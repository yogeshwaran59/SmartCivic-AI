from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

def utc_now():
    return datetime.now(timezone.utc)

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'citizen' | 'worker' | 'authority' | 'admin' | 'journalist'
    contact = db.Column(db.String(20), nullable=False)
    ward = db.Column(db.String(50), nullable=False)  # 'ward_1' | 'ward_2' | 'ward_3'
    gmail = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
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
    description = db.Column(db.Text, nullable=False)
    image_path = db.Column(db.String(255), nullable=True)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(50), nullable=False)  # 'pothole' | 'garbage' | 'drainage' | 'street_light' | 'other'
    priority = db.Column(db.String(20), nullable=False)  # 'High' | 'Medium' | 'Low'
    status = db.Column(db.String(50), nullable=False, default='Submitted')  # 'Submitted' | 'Assigned' | 'In Progress' | 'Resolved' | 'Closed'
    created_at = db.Column(db.DateTime, default=utc_now)
    opened_at = db.Column(db.DateTime, nullable=True)
    escalation_flag = db.Column(db.Boolean, default=False)
    assigned_to = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    ward = db.Column(db.String(50), nullable=False)
    image_analysis = db.Column(db.Text, nullable=True)
    redirected_to_journalist = db.Column(db.Boolean, default=False, nullable=False)
    citizen_gmail = db.Column(db.String(100), nullable=True)

    assigned_worker = db.relationship('User', backref='assigned_complaints')

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def to_dict(self):
        return {
            'complaint_id': self.complaint_id,
            'description': self.description,
            'image_path': self.image_path,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'category': self.category,
            'priority': self.priority,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'opened_at': self.opened_at.isoformat() if self.opened_at else None,
            'escalation_flag': self.escalation_flag,
            'assigned_to': self.assigned_to,
            'assigned_to_name': self.assigned_worker.name if self.assigned_worker else None,
            'ward': self.ward,
            'image_analysis': self.image_analysis,
            'redirected_to_journalist': self.redirected_to_journalist,
            'citizen_gmail': self.citizen_gmail
        }

class StatusLog(db.Model):
    __tablename__ = 'status_logs'
    id = db.Column(db.Integer, primary_key=True)
    complaint_id = db.Column(db.String(50), db.ForeignKey('complaints.complaint_id'), nullable=False)
    status = db.Column(db.String(50), nullable=False)
    notes = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=utc_now)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def to_dict(self):
        return {
            'id': self.id,
            'complaint_id': self.complaint_id,
            'status': self.status,
            'notes': self.notes,
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

