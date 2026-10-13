from datetime import datetime, timedelta, timezone
from typing import Optional
from apscheduler.schedulers.background import BackgroundScheduler
from models import db, Complaint, StatusLog, User, Escalation, log_audit, create_notification

CRITICAL_24HR_CATEGORIES = {
    'drainage', 'open_drain', 'sewage', 'sewage_overflow', 
    'water_leakage', 'manhole', 'fallen_tree'
}

def to_utc(dt: Optional[datetime]) -> datetime:
    """Guarantees offset-aware UTC datetime for resilient comparison across SQLite and Postgres."""
    if dt is None:
        return datetime.now(timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def get_complaint_deadline_threshold(comp, extra_hours: int = 0) -> datetime:
    """
    Computes the timestamp when a complaint breaches its resolution SLA:
    Uses comp.deadline if present; otherwise applies 24h for drainage/critical or 48h for pothole/road issues.
    """
    if comp.deadline is not None:
        dl = to_utc(comp.deadline)
        return dl + timedelta(hours=extra_hours)
    cat = (comp.category or '').lower().strip()
    base_hours = 24 if (cat in CRITICAL_24HR_CATEGORIES or comp.priority == 'High') else 48
    created = to_utc(comp.created_at)
    return created + timedelta(hours=base_hours + extra_hours)

def run_escalation_checks(app):
    with app.app_context():
        now = datetime.now(timezone.utc)

        # -------------------------------------------------------------
        # 1. Check Deadlines and Overdue Status
        # -------------------------------------------------------------
        candidate_overdue = Complaint.query.filter(
            Complaint.status.notin_(['Closed', 'Resolved', 'Rejected']),
            Complaint.deadline != None,
            Complaint.overdue_flag == False
        ).all()
        overdue_complaints = [c for c in candidate_overdue if c.deadline is not None and to_utc(c.deadline) <= now]

        for comp in overdue_complaints:
            comp.overdue_flag = True
            log_audit(
                "COMPLAINT_OVERDUE",
                complaint_id=comp.complaint_id,
                details=f"Complaint passed deadline {comp.deadline.isoformat()}"
            )
            create_notification(
                title=f"Complaint Overdue: {comp.complaint_id}",
                message=f"Complaint {comp.complaint_id} ({comp.category}) in {comp.ward} has exceeded its resolution deadline!",
                ward=comp.ward,
                complaint_id=comp.complaint_id,
                category='overdue'
            )

        # -------------------------------------------------------------
        # 2. Multi-Tier Escalation Engine
        # -------------------------------------------------------------
        # Tier 1: SLA Timer breached (24h for drainage/critical, 48h for pothole/road issues) -> Assistant Commissioner (Level 1)
        active_candidates = Complaint.query.filter(
            Complaint.status.in_(['Submitted', 'Verified', 'Assigned']),
            Complaint.escalation_level < 1
        ).all()
        tier1_candidates = [comp for comp in active_candidates if get_complaint_deadline_threshold(comp, extra_hours=0) <= now]

        for comp in tier1_candidates:
            comp.escalation_flag = True
            comp.escalation_level = 1
            
            supervisor = User.query.filter_by(role='authority', ward=comp.ward).first()
            if not supervisor:
                supervisor = User.query.filter_by(role='authority').first()

            if supervisor:
                comp.assigned_to = supervisor.id
            comp.status = 'Assigned'

            prev_assigned = comp.assigned_worker.name if comp.assigned_worker else "Unassigned"
            new_authority_name = supervisor.name if supervisor else "Assistant Commissioner"
            is_drainage = (comp.category or '').lower() in CRITICAL_24HR_CATEGORIES or comp.priority == 'High'
            sla_hours_text = "24 hours (Drainage/Critical SLA)" if is_drainage else "48 hours (Pothole/Infrastructure SLA)"

            esc = Escalation(
                complaint_id=comp.complaint_id,
                previous_authority=prev_assigned,
                new_authority=new_authority_name,
                escalation_level=1,
                level_name="Assistant Commissioner",
                reason=f"Exceeded {sla_hours_text} without resolution progress",
                is_auto=True
            )
            db.session.add(esc)

            log = StatusLog(
                complaint_id=comp.complaint_id,
                status="Escalated (Tier 1)",
                previous_status=comp.status,
                notes=f"Auto-escalated to {new_authority_name} (Level 1: Assistant Commissioner - {sla_hours_text} breached)"
            )
            db.session.add(log)

            log_audit("AUTO_ESCALATION_TIER1", complaint_id=comp.complaint_id, details=f"Escalated to {new_authority_name}")
            create_notification(
                title=f"Tier 1 Escalation: {comp.complaint_id}",
                message=f"Complaint {comp.complaint_id} ({comp.category}) escalated to Assistant Commissioner ({new_authority_name}) due to {sla_hours_text} timeout",
                ward=comp.ward,
                user_role='authority',
                complaint_id=comp.complaint_id,
                category='escalation'
            )

        # Tier 2: Overdue by additional 24 hours past resolution SLA timer -> Escalate to Zonal Commissioner (Level 2)
        tier2_unresolved = Complaint.query.filter(
            Complaint.status.notin_(['Closed', 'Resolved', 'Rejected']),
            Complaint.escalation_level < 2
        ).all()
        tier2_candidates = [comp for comp in tier2_unresolved if get_complaint_deadline_threshold(comp, extra_hours=24) <= now]

        for comp in tier2_candidates:
            comp.escalation_flag = True
            comp.escalation_level = 2

            higher_auth = User.query.filter_by(role='higher_authority').first()
            new_authority_name = higher_auth.name if higher_auth else "Zonal Commissioner"

            esc = Escalation(
                complaint_id=comp.complaint_id,
                previous_authority="Assistant Commissioner",
                new_authority=new_authority_name,
                escalation_level=2,
                level_name="Zonal Commissioner",
                reason="Unresolved past Level 1 SLA grace period",
                is_auto=True
            )
            db.session.add(esc)

            log = StatusLog(
                complaint_id=comp.complaint_id,
                status="Escalated (Tier 2)",
                previous_status=comp.status,
                notes=f"Auto-escalated to {new_authority_name} (Level 2: Zonal Commissioner)"
            )
            db.session.add(log)

            log_audit("AUTO_ESCALATION_TIER2", complaint_id=comp.complaint_id, details=f"Escalated to {new_authority_name}")
            create_notification(
                title=f"Tier 2 Escalation: {comp.complaint_id}",
                message=f"Complaint {comp.complaint_id} escalated to Zonal Commissioner ({new_authority_name})",
                user_role='higher_authority',
                complaint_id=comp.complaint_id,
                category='escalation'
            )

        # Tier 3: Overdue by additional 48 hours past resolution SLA timer -> Escalate to Municipal Head (Level 3)
        tier3_unresolved = Complaint.query.filter(
            Complaint.status.notin_(['Closed', 'Resolved', 'Rejected']),
            Complaint.escalation_level < 3
        ).all()
        tier3_candidates = [comp for comp in tier3_unresolved if get_complaint_deadline_threshold(comp, extra_hours=48) <= now]

        for comp in tier3_candidates:
            comp.escalation_flag = True
            comp.escalation_level = 3

            esc = Escalation(
                complaint_id=comp.complaint_id,
                previous_authority="Zonal Commissioner",
                new_authority="Municipal Commissioner / Head",
                escalation_level=3,
                level_name="Municipal Commissioner / Head",
                reason="Critical breach unresolved past Level 2 SLA period",
                is_auto=True
            )
            db.session.add(esc)

            log = StatusLog(
                complaint_id=comp.complaint_id,
                status="Escalated (Tier 3)",
                previous_status=comp.status,
                notes="Auto-escalated to Municipal Commissioner / Head (Level 3: Final Escalation)"
            )
            db.session.add(log)

            log_audit("AUTO_ESCALATION_TIER3", complaint_id=comp.complaint_id, details="Escalated to Municipal Commissioner")
            create_notification(
                title=f"CRITICAL Escalation: {comp.complaint_id}",
                message=f"Complaint {comp.complaint_id} reached Tier 3 escalation to Municipal Commissioner!",
                user_role='higher_authority',
                complaint_id=comp.complaint_id,
                category='escalation'
            )

        # -------------------------------------------------------------
        # 3. 5-Minute Journalist Redirection Sweep
        # -------------------------------------------------------------
        j_time_threshold = now - timedelta(minutes=5)
        redirect_candidates = Complaint.query.filter(
            Complaint.status == 'Submitted',
            Complaint.opened_at == None,
            Complaint.redirected_to_journalist == False
        ).all()
        redirect_complaints = [c for c in redirect_candidates if c.created_at is not None and to_utc(c.created_at) <= j_time_threshold]

        for complaint in redirect_complaints:
            complaint.redirected_to_journalist = True
            print(f"[Scheduler] Redirected unopened complaint {complaint.complaint_id} to journalists (5-minute rule)")

        if overdue_complaints or tier1_candidates or tier2_candidates or tier3_candidates or redirect_complaints:
            try:
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                print(f"[Scheduler Commit Error] {e}")

def init_scheduler(app):
    scheduler = BackgroundScheduler()
    scheduler.add_job(func=run_escalation_checks, trigger="interval", seconds=60, args=[app])
    scheduler.start()
    print("[Scheduler] Multi-tier background escalation scheduler running (every 60s).")
    return scheduler
