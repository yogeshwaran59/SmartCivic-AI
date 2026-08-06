from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from models import db, Complaint, StatusLog, User

def run_escalation_checks(app):
    with app.app_context():
        # 1. 48h Authority Escalations
        time_threshold = datetime.utcnow() - timedelta(hours=48)
        escalated_complaints = Complaint.query.filter(
            Complaint.status.in_(['Submitted', 'Assigned']),
            Complaint.created_at <= time_threshold,
            Complaint.escalation_flag == False
        ).all()

        if escalated_complaints:
            print(f"[Scheduler] Found {len(escalated_complaints)} complaints overdue by 48 hours. Running escalations...")

        for complaint in escalated_complaints:
            complaint.escalation_flag = True
            
            # Find a supervisor or higher authority in the same ward, or a general supervisor
            supervisor = User.query.filter_by(role='authority', ward=complaint.ward).first()
            if not supervisor:
                supervisor = User.query.filter_by(role='authority').first()
                
            if supervisor:
                complaint.assigned_to = supervisor.id
                complaint.status = 'Assigned'
                print(f"[Scheduler] Escalated complaint {complaint.complaint_id} to supervisor {supervisor.name} in {complaint.ward}")
            else:
                print(f"[Scheduler] Escalated complaint {complaint.complaint_id} (No supervisor found)")

            # Add status log
            log = StatusLog(
                complaint_id=complaint.complaint_id,
                status="Escalated"
            )
            db.session.add(log)
            
            # Print mock Twilio SMS / Media / Journalist notifications
            print("============================================================")
            print(f"ESCALATION ALERT: Complaint {complaint.complaint_id} has exceeded 48 hours!")
            print(f"MOCK SMS SENT TO CITIZEN: 'Your complaint {complaint.complaint_id} ({complaint.category}) in {complaint.ward} remains unresolved. It has been escalated to Supervisor {supervisor.name if supervisor else 'Ward Head'}.'")
            if supervisor:
                print(f"MOCK SMS SENT TO SUPERVISOR ({supervisor.contact}): 'ALERT: Unresolved complaint {complaint.complaint_id} in {complaint.ward} has been escalated to you.'")
            print(f"MOCK EMAIL SENT TO PRESS WATCHDOG (watchdog@smartcityjournal.org): "
                  f"'Civic Alert: Unresolved 48hr complaint in {complaint.ward}. ID: {complaint.complaint_id}, Category: {complaint.category}, Description: \"{complaint.description}\"'.")
            print("============================================================")
            
        # 2. 5-Minute Journalist Redirection Sweep
        j_time_threshold = datetime.utcnow() - timedelta(minutes=5)
        redirect_complaints = Complaint.query.filter(
            Complaint.status == 'Submitted',
            Complaint.opened_at == None,
            Complaint.created_at <= j_time_threshold,
            Complaint.redirected_to_journalist == False
        ).all()

        for complaint in redirect_complaints:
            complaint.redirected_to_journalist = True
            print(f"[Scheduler] Redirected unopened complaint {complaint.complaint_id} to journalists (5-minute rule)")

        if escalated_complaints or redirect_complaints:
            db.session.commit()

def init_scheduler(app):
    scheduler = BackgroundScheduler()
    # Check every 60 seconds
    scheduler.add_job(func=run_escalation_checks, trigger="interval", seconds=60, args=[app])
    scheduler.start()
    print("[Scheduler] Background scheduler initialized and running (checking every 60 seconds).")
    return scheduler
