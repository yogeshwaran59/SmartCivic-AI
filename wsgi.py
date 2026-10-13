"""
WSGI Entry Point for Production Deployment (Gunicorn / Waitress / Cloud Platforms)
Usage:
  gunicorn wsgi:app
  python wsgi.py
"""
import os
import sys

# Ensure backend directory is on sys.path
backend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend')
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"[SmartCivic AI] WSGI server running on http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
