import os
from flask import Flask, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
from models import db, User
from routes import routes_bp, UPLOAD_FOLDER
from scheduler import init_scheduler

load_dotenv()

def create_app(config=None):
    # Setup flask to serve frontend files from the relative '../frontend' folder
    app = Flask(__name__, static_folder='../frontend', static_url_path='')
    
    # Enable CORS
    CORS(app)
    
    # Configure Database (Neon PostgreSQL if DATABASE_URL is set, otherwise local SQLite)
    database_url = os.getenv('DATABASE_URL')
    if database_url:
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
        app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    else:
        db_path = os.path.join(os.path.dirname(__file__), 'smartcivic.db')
        app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'

    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

    # Apply configuration overrides if provided
    if config:
        app.config.update(config)

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

    # Initialize database
    with app.app_context():
        db.create_all()

    # Initialize APScheduler background escalation (only in non-testing mode)
    if not app.config.get('TESTING'):
        app.config['scheduler'] = init_scheduler(app)

    return app

if __name__ == '__main__':
    app = create_app()
    # Run the server locally on port 5000
    print("[Flask] Starting server at http://127.0.0.1:5000")
    app.run(host='0.0.0.0', port=5000, debug=False)
