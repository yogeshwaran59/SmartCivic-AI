from datetime import datetime, timezone
import os
import sqlite3
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

def utc_now():
    return datetime.now(timezone.utc)

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(30), nullable=False)  # 'citizen' | 'worker' | 'authority' | 'higher_authority' | 'admin' | 'journalist'
    contact = db.Column(db.String(20), nullable=False)
    ward = db.Column(db.String(50), nullable=False)  # 'ward_1' | 'ward_2' | 'ward_3' | 'all'
    gmail = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now)
    approval_status = db.Column(db.String(30), default='approved')  # 'approved' | 'pending_approval' | 'rejected' | 'suspended'
    secret_key = db.Column(db.String(100), nullable=True)  # Generated secret access key e.g. "AUTH-9B7C-4X8A"
    approved_at = db.Column(db.DateTime, nullable=True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def to_dict(self, include_secret=False):
        data = {
            'id': self.id,
            'name': self.name,
            'role': self.role,
            'contact': self.contact,
            'ward': self.ward,
            'gmail': self.gmail,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'approval_status': self.approval_status or 'approved',
            'approved_at': self.approved_at.isoformat() if self.approved_at else None,
            'has_secret_key': bool(self.secret_key)
        }
        if include_secret:
            data['secret_key'] = self.secret_key
        return data

class Complaint(db.Model):
    __tablename__ = 'complaints'
    complaint_id = db.Column(db.String(50), primary_key=True)
    title = db.Column(db.String(200), nullable=True)
    description = db.Column(db.Text, nullable=False)
    image_path = db.Column(db.String(255), nullable=True)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(50), nullable=False)  # 'pothole' | 'garbage' | 'drainage' | 'street_light' | etc.
    priority = db.Column(db.String(20), nullable=False)  # 'High' | 'Medium' | 'Low'
    status = db.Column(db.String(50), nullable=False, default='Submitted')  # 'Submitted' | 'Verified' | 'Assigned' | 'In Progress' | 'Completed' | 'Closed' | 'Rejected' | 'Reopened'
    created_at = db.Column(db.DateTime, default=utc_now)
    opened_at = db.Column(db.DateTime, nullable=True)
    verified_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    closed_at = db.Column(db.DateTime, nullable=True)
    deadline = db.Column(db.DateTime, nullable=True)
    rejection_reason = db.Column(db.Text, nullable=True)
    reopen_count = db.Column(db.Integer, default=0)
    reopened_reason = db.Column(db.Text, nullable=True)
    duplicate_of_id = db.Column(db.String(50), nullable=True)
    escalation_flag = db.Column(db.Boolean, default=False)
    escalation_level = db.Column(db.Integer, default=0)  # 0: None, 1: Supervisor/Asst Comm, 2: Commissioner, 3: Municipal Head
    overdue_flag = db.Column(db.Boolean, default=False)
    assigned_to = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    ward = db.Column(db.String(50), nullable=False)
    image_analysis = db.Column(db.Text, nullable=True)
    redirected_to_journalist = db.Column(db.Boolean, default=False, nullable=False)
    citizen_gmail = db.Column(db.String(100), nullable=True)

    # Evidence image references
    before_image_path = db.Column(db.String(255), nullable=True)
    progress_image_path = db.Column(db.String(255), nullable=True)
    resolved_image_path = db.Column(db.String(255), nullable=True)
    inspection_image_path = db.Column(db.String(255), nullable=True)
    inspection_notes = db.Column(db.Text, nullable=True)

    # Citizen feedback
    citizen_rating = db.Column(db.Integer, nullable=True)  # 1-5 stars
    citizen_feedback = db.Column(db.Text, nullable=True)
    citizen_satisfied = db.Column(db.Boolean, nullable=True)

    assigned_worker = db.relationship('User', backref='assigned_complaints')

    @property
    def id(self):
        return self.complaint_id

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def to_dict(self):
        return {
            'complaint_id': self.complaint_id,
            'title': self.title or (f"{self.category.capitalize()} in {self.ward.replace('_', ' ').title()}"),
            'description': self.description,
            'image_path': self.image_path,
            'before_image_path': self.before_image_path,
            'progress_image_path': self.progress_image_path,
            'resolved_image_path': self.resolved_image_path,
            'inspection_image_path': self.inspection_image_path,
            'inspection_notes': self.inspection_notes,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'category': self.category,
            'priority': self.priority,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'opened_at': self.opened_at.isoformat() if self.opened_at else None,
            'verified_at': self.verified_at.isoformat() if self.verified_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'closed_at': self.closed_at.isoformat() if self.closed_at else None,
            'deadline': self.deadline.isoformat() if self.deadline else None,
            'rejection_reason': self.rejection_reason,
            'reopen_count': self.reopen_count or 0,
            'reopened_reason': self.reopened_reason,
            'duplicate_of_id': self.duplicate_of_id,
            'escalation_flag': self.escalation_flag,
            'escalation_level': self.escalation_level or 0,
            'overdue_flag': self.overdue_flag,
            'assigned_to': self.assigned_to,
            'assigned_to_name': self.assigned_worker.name if self.assigned_worker else None,
            'ward': self.ward,
            'image_analysis': self.image_analysis,
            'redirected_to_journalist': self.redirected_to_journalist,
            'citizen_gmail': self.citizen_gmail,
            'citizen_rating': self.citizen_rating,
            'citizen_feedback': self.citizen_feedback,
            'citizen_satisfied': self.citizen_satisfied
        }

class StatusLog(db.Model):
    __tablename__ = 'status_logs'
    id = db.Column(db.Integer, primary_key=True)
    complaint_id = db.Column(db.String(50), db.ForeignKey('complaints.complaint_id'), nullable=False)
    status = db.Column(db.String(50), nullable=False)
    previous_status = db.Column(db.String(50), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    user_id = db.Column(db.Integer, nullable=True)
    user_name = db.Column(db.String(100), nullable=True)
    user_role = db.Column(db.String(50), nullable=True)
    timestamp = db.Column(db.DateTime, default=utc_now)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def to_dict(self):
        return {
            'id': self.id,
            'complaint_id': self.complaint_id,
            'status': self.status,
            'previous_status': self.previous_status,
            'notes': self.notes,
            'user_id': self.user_id,
            'user_name': self.user_name,
            'user_role': self.user_role,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None
        }

class ComplaintEvidence(db.Model):
    __tablename__ = 'complaint_evidences'
    id = db.Column(db.Integer, primary_key=True)
    complaint_id = db.Column(db.String(50), db.ForeignKey('complaints.complaint_id'), nullable=False)
    evidence_type = db.Column(db.String(50), nullable=False)  # 'citizen' | 'inspection' | 'before' | 'progress' | 'after'
    file_path = db.Column(db.String(255), nullable=False)
    file_type = db.Column(db.String(20), default='image')  # 'image' | 'video'
    uploader_id = db.Column(db.Integer, nullable=True)
    uploader_name = db.Column(db.String(100), nullable=True)
    uploader_role = db.Column(db.String(50), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now)

    def to_dict(self):
        return {
            'id': self.id,
            'complaint_id': self.complaint_id,
            'evidence_type': self.evidence_type,
            'file_path': self.file_path,
            'file_type': self.file_type,
            'uploader_id': self.uploader_id,
            'uploader_name': self.uploader_name,
            'uploader_role': self.uploader_role,
            'notes': self.notes,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class Notification(db.Model):
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=True)
    user_role = db.Column(db.String(50), nullable=True)
    ward = db.Column(db.String(50), nullable=True)
    recipient_email = db.Column(db.String(100), nullable=True)
    complaint_id = db.Column(db.String(50), nullable=True)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(50), default='info')  # 'submission' | 'verification' | 'assignment' | 'progress' | 'completion' | 'escalation' | 'reopen' | 'overdue'
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=utc_now)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'user_role': self.user_role,
            'ward': self.ward,
            'recipient_email': self.recipient_email,
            'complaint_id': self.complaint_id,
            'title': self.title,
            'message': self.message,
            'category': self.category,
            'is_read': self.is_read,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class Comment(db.Model):
    __tablename__ = 'comments'
    id = db.Column(db.Integer, primary_key=True)
    complaint_id = db.Column(db.String(50), db.ForeignKey('complaints.complaint_id'), nullable=False)
    user_id = db.Column(db.Integer, nullable=True)
    user_name = db.Column(db.String(100), nullable=False)
    user_role = db.Column(db.String(50), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now)

    def to_dict(self):
        return {
            'id': self.id,
            'complaint_id': self.complaint_id,
            'user_id': self.user_id,
            'user_name': self.user_name,
            'user_role': self.user_role,
            'message': self.message,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class Feedback(db.Model):
    __tablename__ = 'feedbacks'
    id = db.Column(db.Integer, primary_key=True)
    complaint_id = db.Column(db.String(50), db.ForeignKey('complaints.complaint_id'), nullable=False)
    citizen_gmail = db.Column(db.String(100), nullable=True)
    rating = db.Column(db.Integer, nullable=False)  # 1 - 5
    satisfaction = db.Column(db.String(20), nullable=False)  # 'satisfactory' | 'unsatisfactory'
    comment = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now)

    def to_dict(self):
        return {
            'id': self.id,
            'complaint_id': self.complaint_id,
            'citizen_gmail': self.citizen_gmail,
            'rating': self.rating,
            'satisfaction': self.satisfaction,
            'comment': self.comment,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class Escalation(db.Model):
    __tablename__ = 'escalations'
    id = db.Column(db.Integer, primary_key=True)
    complaint_id = db.Column(db.String(50), db.ForeignKey('complaints.complaint_id'), nullable=False)
    previous_authority = db.Column(db.String(100), nullable=True)
    new_authority = db.Column(db.String(100), nullable=True)
    escalation_level = db.Column(db.Integer, default=1)  # 1: Asst Commissioner, 2: Commissioner, 3: Municipal Head
    level_name = db.Column(db.String(100), default='Assistant Commissioner')
    reason = db.Column(db.Text, nullable=False)
    is_auto = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=utc_now)

    def to_dict(self):
        return {
            'id': self.id,
            'complaint_id': self.complaint_id,
            'previous_authority': self.previous_authority,
            'new_authority': self.new_authority,
            'escalation_level': self.escalation_level,
            'level_name': self.level_name,
            'reason': self.reason,
            'is_auto': self.is_auto,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    id = db.Column(db.Integer, primary_key=True)
    complaint_id = db.Column(db.String(50), nullable=True)
    user_id = db.Column(db.Integer, nullable=True)
    user_name = db.Column(db.String(100), default='System')
    user_role = db.Column(db.String(50), default='system')
    action = db.Column(db.String(100), nullable=False)
    details = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=utc_now)

    def to_dict(self):
        return {
            'id': self.id,
            'complaint_id': self.complaint_id,
            'user_id': self.user_id,
            'user_name': self.user_name,
            'user_role': self.user_role,
            'action': self.action,
            'details': self.details,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None
        }

class JournalistReport(db.Model):
    __tablename__ = 'journalist_reports'
    id = db.Column(db.Integer, primary_key=True)
    complaint_id = db.Column(db.String(50), db.ForeignKey('complaints.complaint_id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    published = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now)

    complaint = db.relationship('Complaint', backref='reports')

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def to_dict(self):
        return {
            'id': self.id,
            'complaint_id': self.complaint_id,
            'title': self.title,
            'content': self.content,
            'published': self.published,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

def log_audit(action, complaint_id=None, user=None, details=None, user_id=None, user_name=None, user_role=None, **kwargs):
    """Utility helper to record an audit entry."""
    try:
        uid = user_id or (user.id if user and hasattr(user, 'id') else (user.get('id') if isinstance(user, dict) else None))
        uname = user_name or (user.name if user and hasattr(user, 'name') else (user.get('name') if isinstance(user, dict) else 'System'))
        urole = user_role or (user.role if user and hasattr(user, 'role') else (user.get('role') if isinstance(user, dict) else 'system'))
        entry = AuditLog(
            complaint_id=complaint_id,
            user_id=uid,
            user_name=uname,
            user_role=urole,
            action=action,
            details=details
        )
        db.session.add(entry)
        db.session.commit()
    except Exception as e:
        print(f"[AuditLog Error] {e}")

def create_notification(title, message, user_id=None, user_role=None, ward=None, recipient_email=None, complaint_id=None, category='info'):
    """Utility helper to create a persistent in-app notification."""
    try:
        notif = Notification(
            user_id=user_id,
            user_role=user_role,
            ward=ward,
            recipient_email=recipient_email,
            complaint_id=complaint_id,
            title=title,
            message=message,
            category=category,
            is_read=False
        )
        db.session.add(notif)
        db.session.commit()
        return notif
    except Exception as e:
        print(f"[Notification Error] {e}")
        return None

def auto_migrate_db(engine_or_db):
    """
    Safely adds missing columns to existing tables for SQLite and PostgreSQL.
    """
    column_definitions = {
        'complaints': [
            ("title", "VARCHAR(200)"),
            ("verified_at", "DATETIME"),
            ("completed_at", "DATETIME"),
            ("closed_at", "DATETIME"),
            ("deadline", "DATETIME"),
            ("rejection_reason", "TEXT"),
            ("reopen_count", "INTEGER DEFAULT 0"),
            ("reopened_reason", "TEXT"),
            ("duplicate_of_id", "VARCHAR(50)"),
            ("escalation_level", "INTEGER DEFAULT 0"),
            ("overdue_flag", "BOOLEAN DEFAULT FALSE"),
            ("before_image_path", "VARCHAR(255)"),
            ("progress_image_path", "VARCHAR(255)"),
            ("resolved_image_path", "VARCHAR(255)"),
            ("inspection_image_path", "VARCHAR(255)"),
            ("inspection_notes", "TEXT"),
            ("citizen_rating", "INTEGER"),
            ("citizen_feedback", "TEXT"),
            ("citizen_satisfied", "BOOLEAN")
        ],
        'status_logs': [
            ("previous_status", "VARCHAR(50)"),
            ("user_id", "INTEGER"),
            ("user_name", "VARCHAR(100)"),
            ("user_role", "VARCHAR(50)")
        ],
        'users': [
            ("created_at", "DATETIME DEFAULT '2000-01-01 00:00:00'"),
            ("approval_status", "VARCHAR(30) DEFAULT 'approved'"),
            ("secret_key", "VARCHAR(100)"),
            ("approved_at", "DATETIME")
        ],
        'notifications': [
            ("user_id", "INTEGER"),
            ("user_role", "VARCHAR(50)"),
            ("ward", "VARCHAR(50)"),
            ("recipient_email", "VARCHAR(100)"),
            ("category", "VARCHAR(50) DEFAULT 'info'")
        ]
    }

    try:
        from sqlalchemy import inspect, text
        engine = engine_or_db.engine if hasattr(engine_or_db, 'engine') else engine_or_db
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()

        for table_name, cols in column_definitions.items():
            if table_name in existing_tables:
                existing_cols = [c['name'] for c in inspector.get_columns(table_name)]
                for col_name, col_type in cols:
                    if col_name not in existing_cols:
                        try:
                            # Adjust type for Postgres if needed
                            sql_type = col_type
                            if 'sqlite' not in str(engine.url):
                                if 'DATETIME' in sql_type:
                                    sql_type = sql_type.replace('DATETIME', 'TIMESTAMP')
                                if 'BOOLEAN' in sql_type:
                                    sql_type = 'BOOLEAN DEFAULT FALSE'
                            query = f"ALTER TABLE {table_name} ADD COLUMN {col_name} {sql_type};"
                            with engine.connect() as conn:
                                conn.execute(text(query))
                                conn.commit()
                            print(f"[DB Migration] Added column '{col_name}' to '{table_name}'")
                        except Exception as add_err:
                            print(f"[DB Migration Notice] {table_name}.{col_name}: {add_err}")
    except Exception as e:
        print(f"[DB Migration Error] {e}")
