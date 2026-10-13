# 🚀 SmartCivic AI - Complete Production Deployment Guide

This guide details how to deploy **SmartCivic AI** to production on any cloud platform or server.

---

## 📋 Architectural Overview

- **Frontend**: Single Page Application (HTML5, Vanilla CSS Glassmorphism, JavaScript, Leaflet GIS mapping, Chart.js).
- **Backend**: Python 3.11+ Flask Application with WSGI entry point (`wsgi.py`).
- **Database**: Remote Cloud PostgreSQL (Neon DB with SSL) or local SQLite fallback.
- **Background Tasks**: Multi-tier APScheduler running auto-escalations every 60 seconds.
- **Production WSGI Server**: Gunicorn (Linux/Containers) / Waitress (Windows).
- **Integrations**: 24/7 Exotel IVR Webhook (`/api/exotel/webhook`), Hugging Face Multilingual AI, Gmail SMTP Alerts.

---

## ✅ Deployment Pre-Flight Checklist (Already Configured)

- [x] **Dynamic Base URL**: `frontend/app.js` automatically adapts to your live production domain (resolving API requests to the active host instead of localhost).
- [x] **WSGI Entry Point**: `wsgi.py` handles backend module resolution and boots `create_app()` cleanly.
- [x] **Cloud Port Detection**: `PORT` environment variable dynamically parsed (supports Render, Railway, Heroku, Cloud Run).
- [x] **Health Check Endpoint**: `/api/health` and `/health` respond with `HTTP 200` for container orchestrators.
- [x] **Unified Requirements**: `requirements.txt` at repository root includes `gunicorn`, `waitress`, `psycopg2-binary`, `flask-cors`, etc.
- [x] **Smart SLA Timers**: Category-aware resolution timers configured (24h for Drainage & critical emergencies; 48h for Potholes & road infrastructure issues).
- [x] **Container Ready**: Production `Dockerfile` and `.dockerignore` included.
- [x] **Infrastructure as Code**: `render.yaml` Blueprint and `Procfile` ready for zero-friction git pushes.

---

## 🌐 Option 1: Deploy on Render (Recommended - Free Tier & Fast Setup)

[Render](https://render.com) offers seamless Python hosting with automatic SSL certificates.

### Step 1: Push Repository to GitHub
Ensure all recent changes are committed and pushed:
```bash
git add .
git commit -m "Configure production WSGI, Dockerfile, and deployment files"
git push origin main
```

### Step 2: Create Web Service on Render
1. Log in to [dashboard.render.com](https://dashboard.render.com/).
2. Click **New +** → **Web Service**.
3. Select your GitHub repository (`SmartCivic-AI`).
4. Configure service settings:
   - **Name**: `smartcivic-ai` (or your chosen name)
   - **Region**: Closest to your users (e.g., Singapore or Oregon)
   - **Branch**: `main`
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn wsgi:app`
   - **Plan**: `Free`

### Step 3: Add Environment Variables in Render Dashboard
Go to the **Environment** tab in your Render service and add:

| Key | Example Value | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql://neondb_owner:...@...neon.tech/neondb?sslmode=require` | Your Neon PostgreSQL connection string |
| `SECRET_KEY` | `smartcivic_admin_secret_session_key_2026_supersecure` | Session encryption key |
| `APP_BASE_URL` | `https://your-app-name.onrender.com` | Your live Render URL (for email links) |
| `ENABLE_EMAIL_NOTIFICATIONS` | `true` | Enables real-time dispatch alerts |
| `SMTP_SERVER` | `smtp.gmail.com` | SMTP host |
| `SMTP_PORT` | `587` | SMTP port |
| `SMTP_USER` | `your_email@gmail.com` | Your Gmail address |
| `SMTP_PASSWORD` | `your_16_char_app_password` | Gmail App Password |
| `SENDER_EMAIL` | `your_email@gmail.com` | Outgoing sender email |
| `ADMIN_EMAIL` | `admin@smartcivic.ai` | Master Admin portal email |
| `ADMIN_PASSWORD` | `Admin@SmartCivic2026` | Master Admin portal password |
| `ADMIN_SECRET_PIN` | `7890` | Master Admin login PIN |
| `EXOTEL_SID` | `your_sid` | (Optional) Exotel IVR SID |
| `EXOTEL_API_KEY` | `your_key` | (Optional) Exotel API Key |
| `EXOTEL_API_TOKEN` | `your_token` | (Optional) Exotel Token |
| `EXOTEL_SUBDOMAIN` | `api.exotel.com` | (Optional) Exotel Subdomain |
| `EXOTEL_CALLER_ID` | `09513886363` | (Optional) Exotel Hotline Number |

### Step 4: Deploy & Verify
- Render will install dependencies and start Gunicorn.
- Visit `https://your-app-name.onrender.com/` in your browser.
- Verify health: `https://your-app-name.onrender.com/api/health`.

---

## 🚆 Option 2: Deploy on Railway

1. Go to [railway.app](https://railway.app) and click **New Project** → **Deploy from GitHub repo**.
2. Select your repository.
3. Railway automatically detects `Procfile` (`web: gunicorn wsgi:app`).
4. Click **Variables** and paste the environment variables from the table above.
5. In **Settings** → **Networking**, click **Generate Domain** (e.g. `smartcivic-production.up.railway.app`).
6. Update `APP_BASE_URL` with that generated URL.

---

## 🐳 Option 3: Deploy with Docker (AWS ECS, Google Cloud Run, DigitalOcean, VPS)

### Build the Docker Container
```bash
docker build -t smartcivic-ai .
```

### Run the Docker Container
```bash
docker run -d \
  --name smartcivic-app \
  -p 5000:5000 \
  --env-file backend/.env \
  smartcivic-ai
```
The application will be live at `http://localhost:5000`.

---

## 🐧 Option 4: Linux VPS (Ubuntu / Debian with Systemd & Nginx)

### 1. Clone & Set Up Virtual Environment on VPS
```bash
git clone https://github.com/yogeshwaran59/SmartCivic-AI.git /var/www/smartcivic
cd /var/www/smartcivic
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp backend/.env.example backend/.env
# Edit backend/.env with your production values
nano backend/.env
```

### 2. Configure Systemd Service
Create `/etc/systemd/system/smartcivic.service`:
```ini
[Unit]
Description=SmartCivic AI Gunicorn Service
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/smartcivic
Environment="PATH=/var/www/smartcivic/.venv/bin"
ExecStart=/var/www/smartcivic/.venv/bin/gunicorn --workers 3 --bind 127.0.0.1:5000 wsgi:app
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable smartcivic
sudo systemctl start smartcivic
```

### 3. Configure Nginx Reverse Proxy
Create `/etc/nginx/sites-available/smartcivic`:
```nginx
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;

    client_max_body_size 25M;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```
Enable site and add SSL via Let's Encrypt:
```bash
sudo ln -s /etc/nginx/sites-available/smartcivic /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl restart nginx
sudo certbot --nginx -d yourdomain.com
```

---

## 🪟 Option 5: Local / Windows Server Production Hosting

To run in production mode on a Windows server using Waitress:
```powershell
.\.venv\Scripts\activate
python -m waitress --listen=0.0.0.0:5000 wsgi:app
```

---

## 🔗 Post-Deployment Configuration

### 1. Update Exotel IVR Webhook
Once deployed to your live domain (e.g. `https://smartcivic-ai.onrender.com`), update your Exotel Flow Builder:
- **Passthru URL**: `https://smartcivic-ai.onrender.com/api/exotel/webhook`
- Method: `POST` / `GET`
Now citizen hotline calls will immediately reach your production application!

### 2. Default Demo Accounts
The database automatically seeds demo accounts for testing all user roles:
- **Authority / Ward Supervisor**: `suresh@gmail.com` / `password`
- **Field Worker**: `ramesh@gmail.com` / `password`
- **Citizen**: `anita@gmail.com` / `password`
- **Journalist**: `journalist@gmail.com` / `password`
- **Higher Authority**: `commissioner@smartcivic.ai` / `password` (Key: `AUTH-HIGH-2026`)
- **Master Admin Portal**: Navigate to `/admin/login` → `admin@smartcivic.ai` / `Admin@SmartCivic2026` / PIN: `7890`
