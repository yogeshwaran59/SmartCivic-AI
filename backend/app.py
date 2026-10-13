import os
import sys

# Ensure backend directory is in sys.path so modules resolve whether run from root or backend
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from flask import Flask, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
from models import db, User
from routes import routes_bp, UPLOAD_FOLDER
from scheduler import init_scheduler

load_dotenv()

_cached_db_hostaddr = None

def get_db_hostaddr(database_url):
    """
    If local/Wi-Fi DNS fails to resolve Neon hostname (e.g. 'Query refused' on restricted Wi-Fi),
    resolve via Google DNS over HTTPS to obtain the IPv4 address directly for psycopg2 hostaddr.
    """
    global _cached_db_hostaddr
    if _cached_db_hostaddr:
        return _cached_db_hostaddr
    try:
        import socket
        from urllib.parse import urlparse
        parsed = urlparse(database_url)
        hostname = parsed.hostname
        if not hostname:
            return None
        try:
            socket.gethostbyname(hostname)
            return None  # Standard OS DNS resolved successfully
        except Exception:
            pass

        import urllib.request
        import json
        req = urllib.request.Request(f'https://dns.google/resolve?name={hostname}', headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode('utf-8'))
            for ans in data.get('Answer', []):
                if ans.get('type') == 1:
                    _cached_db_hostaddr = ans.get('data')
                    print(f"[DNS Resilience] Resolved database host '{hostname}' -> {_cached_db_hostaddr} via Google DNS.")
                    return _cached_db_hostaddr
    except Exception as exc:
        print(f"[DNS Resilience Notice] Fallback DNS query: {exc}")
    return None

def create_app(config=None):
    # Setup flask to serve frontend files with absolute path resolution
    frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'frontend'))
    app = Flask(__name__, static_folder=frontend_dir, static_url_path='')
    
    # Enable CORS
    cors = CORS()
    cors.init_app(app)  # type: ignore[arg-type]
    
    # Configure Database (Neon PostgreSQL if DATABASE_URL is set, otherwise local SQLite)
    database_url = os.getenv('DATABASE_URL')
    if database_url:
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
        app.config['SQLALCHEMY_DATABASE_URI'] = database_url
        
        connect_args = {'connect_timeout': 10}
        hostaddr = get_db_hostaddr(database_url)
        if hostaddr:
            connect_args['hostaddr'] = hostaddr

        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            'pool_pre_ping': True,
            'pool_recycle': 280,
            'connect_args': connect_args
        }
    else:
        db_path = os.path.join(os.path.dirname(__file__), 'smartcivic.db')
        app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            'pool_pre_ping': True,
            'pool_recycle': 280
        }

    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'smartcivic_admin_secret_session_key_2026_supersecure')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

    # Apply configuration overrides if provided
    if config:
        app.config.update(config)
        if 'sqlite' in app.config.get('SQLALCHEMY_DATABASE_URI', ''):
            app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
                'pool_pre_ping': True,
                'pool_recycle': 280
            }

    # Initialize extensions
    db.init_app(app)

    # Register blueprints
    app.register_blueprint(routes_bp)

    # Route to serve front-end index.html
    @app.route('/')
    def serve_frontend():
        return app.send_static_file('index.html')

    # Serve uploaded images
    @app.route('/uploads/<path:filename>')
    def serve_uploads(filename):
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

    # Initialize database with Neon PostgreSQL
    with app.app_context():
        try:
            db.create_all()
            from models import auto_migrate_db
            auto_migrate_db(db)
            print("[Database] Successfully connected and initialized database.")
            # Auto-seed initial demo accounts if database is fresh/empty
            if User.query.count() == 0:
                print("[Database Seed] Seeding default demo accounts into database...")
                demo_users = [
                    User(name="Supervisor Suresh", role="authority", contact="+919876543210", ward="ward_1", gmail="suresh@gmail.com", password="password"),
                    User(name="Worker Ramesh", role="worker", contact="+919876543211", ward="ward_1", gmail="ramesh@gmail.com", password="password"),
                    User(name="Citizen Anita", role="citizen", contact="+919876543212", ward="ward_1", gmail="anita@gmail.com", password="password"),
                    User(name="Journalist Press", role="journalist", contact="+919876543213", ward="ward_1", gmail="journalist@gmail.com", password="password"),
                    User(name="Commissioner Rao", role="higher_authority", contact="+919876543214", ward="all", gmail="commissioner@smartcivic.ai", password="password", approval_status="approved", secret_key="AUTH-HIGH-2026")
                ]
                db.session.add_all(demo_users)
                db.session.commit()
                print("[Database Seed] Default demo accounts seeded successfully.")
        except Exception as db_err:
            print(f"[Database Warning] Database initialization notice: {db_err}")

    # Initialize APScheduler background escalation (only in non-testing mode)
    if not app.config.get('TESTING'):
        app.config['scheduler'] = init_scheduler(app)

    return app

if __name__ == '__main__':
    app = create_app()
    port = int(os.environ.get('PORT', 5000))
    print(f"[Flask] Starting server at http://0.0.0.0:{port}")
    app.run(host='0.0.0.0', port=port, debug=False)
