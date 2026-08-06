from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'citizen' | 'worker' | 'authority'
    contact = db.Column(db.String(20), nullable=False)
    ward = db.Column(db.String(50), nullable=False)  # 'ward_1' | 'ward_2' | 'ward_3'
    gmail = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'role': self.role,
            'contact': self.contact,
            'ward': self.ward,
            'gmail': self.gmail,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    opened_at = db.Column(db.DateTime, nullable=True)
    escalation_flag = db.Column(db.Boolean, default=False)
    assigned_to = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    ward = db.Column(db.String(50), nullable=False)
    image_analysis = db.Column(db.Text, nullable=True)
    redirected_to_journalist = db.Column(db.Boolean, default=False, nullable=False)

    assigned_worker = db.relationship('User', backref='assigned_complaints')

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
            'redirected_to_journalist': self.redirected_to_journalist
        }

class StatusLog(db.Model):
    __tablename__ = 'status_logs'
    id = db.Column(db.Integer, primary_key=True)
    complaint_id = db.Column(db.String(50), db.ForeignKey('complaints.complaint_id'), nullable=False)
    status = db.Column(db.String(50), nullable=False)
    notes = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    complaint = db.relationship('Complaint', backref='reports')

    def to_dict(self):
        return {
            'id': self.id,
            'complaint_id': self.complaint_id,
            'title': self.title,
            'content': self.content,
            'published': self.published,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
