import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

# pyrefly: ignore [missing-import]
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), 'backend', '.env'))

# pyrefly: ignore [missing-import]
from app import create_app
# pyrefly: ignore [missing-import]
from models import User

app = create_app({'TESTING': True})
with app.app_context():
    users = User.query.all()
    print(f"\n{'='*60}")
    print(f"Total users in database: {len(users)}")
    print(f"{'='*60}")
    for u in users:
        print(f"  Name: {u.name:20s} | Gmail: {u.gmail:30s} | Role: {u.role:12s} | Status: {u.approval_status}")
    print(f"{'='*60}")
