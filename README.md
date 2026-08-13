# 🏙️ SmartCivic AI - Intelligent Civic Issue Reporting & Dispatch System

An end-to-end civic complaint management platform featuring an AI-driven web portal, Leaflet heatmap analytics, real-time worker task dispatching, journalist escalation tracking, and a **24/7 Exotel IVR Phone Hotline**.

---

## 🚀 Key Features

1. **Citizen Web Portal**:
   - Report civic issues (Pothole, Drainage, Garbage, Street Light, Footpath, Manhole) with text & proof image uploads.
   - Quick-select category dropdown & automatic GPS location pinning.
   - Real-time complaint tracking timeline with ID search.

2. **24/7 Exotel IVR Phone Hotline**:
   - Phone hotline integration via Exotel Flow Builder & Passthru Webhook (`/api/exotel/webhook`).
   - Automatically parses DTMF keypad inputs (`1-6`), creates complaints in DB, determines ward priority, and sends confirmation SMS.

3. **Authority Dashboard**:
   - Regional heatmap analytics & ward severity status (Red > 5, Yellow 3-5, Green 1-2).
   - One-click worker assignment with live Leaflet route mapping.

4. **Worker Module**:
   - Real-time task view for field workers with interactive route map & photo upload resolution.

5. **Journalist Escalation & Portal**:
   - **5-Minute Auto Escalation Rule**: Unopened/unassigned complaints automatically redirect to the Journalist portal after 5 minutes via APScheduler background worker.

---

## 🛠️ Project Structure

```text
project/
├── backend/
│   ├── app.py               # Flask application entry point
│   ├── routes.py            # API routes & Exotel IVR Webhooks
│   ├── models.py            # SQLAlchemy Database Models (User, Complaint, StatusLog, JournalistReport)
│   ├── ai_processor.py      # AI text classifier & image similarity duplicate detection
│   ├── scheduler.py         # APScheduler 5-minute escalation background task
│   ├── requirements.txt     # Python dependencies
│   ├── .env.example         # Environment variables template
│   └── uploads/             # Directory for complaint & resolution images
├── frontend/
│   ├── index.html           # Single-page web application UI
│   ├── app.css              # Glassmorphic dark styling & responsive design
│   └── app.js               # Frontend JavaScript logic & Leaflet map integrations
├── alter_db.py              # Database schema migration helper
├── setup.bat                # One-click setup for Windows
├── setup.sh                 # One-click setup for Mac / Linux
├── .gitignore               # Git ignore rules
└── README.md                # Project documentation (this file)
```


---

## 💻 Teammate Setup Guide

Follow these steps to run the complete project locally:

### 1. Prerequisites
- **Python 3.9+** installed ([download](https://www.python.org/downloads/))
- **Git** installed ([download](https://git-scm.com/downloads))
- **pip** (comes bundled with Python)
- **ngrok** (optional, only needed for testing Exotel IVR hotline locally)

### 2. Clone the Repository
```bash
git clone <your-repository-url>
cd project
```

### 3. Quick Setup (Recommended)

**Windows** — double-click or run in terminal:
```powershell
.\setup.bat
```

**Mac / Linux:**
```bash
bash setup.sh
```

This will automatically:
- Create a `.venv` virtual environment
- Install all Python dependencies
- Copy `.env.example` → `.env` (you'll need to fill in your credentials)

### 4. Manual Setup (If you prefer)

<details>
<summary>Click to expand manual steps</summary>

#### Create & Activate Virtual Environment

**Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\activate
```

**Mac / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

#### Install Dependencies
```bash
pip install -r backend/requirements.txt
```

#### Configure Environment Variables
```bash
cp backend/.env.example backend/.env
```

Edit `backend/.env` with your credentials:
```ini
# Shared Neon PostgreSQL Database URL (Leave empty to use local SQLite)
DATABASE_URL=postgresql://neondb_owner:...@ep-spring-boat-amj7v6lt-pooler.c-5.us-east-1.aws.neon.tech/neondb?sslmode=require

# Exotel Credentials
EXOTEL_SID=your_exotel_sid
EXOTEL_API_KEY=your_exotel_api_key
EXOTEL_API_TOKEN=your_exotel_api_token
EXOTEL_SUBDOMAIN=api.exotel.com
EXOTEL_CALLER_ID=your_exotel_caller_id
```

</details>

> **Note:** If `DATABASE_URL` is provided, all team members will share the same live PostgreSQL database on Neon. If `DATABASE_URL` is omitted, Flask will fallback to a local SQLite database (`backend/smartcivic.db`).

---

## 🏃 Running the Application

### 1. Activate Virtual Environment (if not already active)

**Windows:**
```powershell
.\.venv\Scripts\activate
```

**Mac / Linux:**
```bash
source .venv/bin/activate
```

### 2. Start the Flask Server
```bash
python backend/app.py
```
The application will start at:
👉 **`http://127.0.0.1:5000`** (or `http://localhost:5000`)

### 3. Access Web Application
Open your browser and navigate to `http://127.0.0.1:5000`. You can log in using default seed accounts or create a new user account on the signup page.

---

## 📞 Setting Up Exotel IVR Hotline (Optional)

1. Start ngrok in a separate terminal:
   ```bash
   ngrok http 5000
   ```
2. Copy the HTTPS forwarding URL (e.g. `https://xxxx.ngrok-free.dev`).
3. Log in to [my.exotel.com](https://my.exotel.com) → **App Bazaar** → **Flow Builder**.
4. Configure your flow:
   - **Greeting** → Welcome prompt
   - **Gather** → 1 digit input
   - **Passthru** → URL: `https://xxxx.ngrok-free.dev/api/exotel/webhook` (Method: POST/GET)
   - **Greeting** → Thank you confirmation & Hangup
5. Save the flow and dial your Exotel phone number!

---

## 🔧 Troubleshooting

| Issue | Solution |
|-------|----------|
| `python` not recognized | Use `python3` instead, or add Python to your system PATH |
| `pip install` fails | Make sure your virtual environment is activated first |
| Port 5000 already in use | Kill the existing process or change the port in `backend/app.py` |
| Database errors on first run | The database is auto-created on startup — just restart the server |
| `.env` not loading | Ensure `backend/.env` exists (copy from `backend/.env.example`) |

