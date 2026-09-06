import os
import smtplib
import threading
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

def is_email_enabled():
    enabled_str = os.getenv('ENABLE_EMAIL_NOTIFICATIONS', 'true').strip().lower()
    return enabled_str in ['true', '1', 'yes']

def send_email_async(to_email, subject, html_content, text_content="", sender_gmail=None, sender_password=None):
    """
    Spawns a daemon thread to send an email asynchronously without blocking Flask request.
    Can accept optional sender_gmail and sender_password provided during signup/login.
    """
    if not to_email or not is_email_enabled():
        return

    thread = threading.Thread(
        target=_dispatch_email_smtp,
        args=(to_email, subject, html_content, text_content, sender_gmail, sender_password)
    )
    thread.daemon = True
    thread.start()

def _dispatch_email_smtp(to_email, subject, html_content, text_content, sender_gmail=None, sender_password=None):
    load_dotenv(override=True)
    smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
    smtp_port = int(os.getenv('SMTP_PORT', '587'))
    
    # Try custom user credentials first if provided
    if sender_gmail and sender_password:
        use_custom = True
        smtp_user = sender_gmail.strip()
        smtp_password = sender_password.strip()
    else:
        use_custom = False
        smtp_user = (os.getenv('SMTP_USER') or '').strip()
        smtp_password = (os.getenv('SMTP_PASSWORD') or '').strip()
    
    # Fallback to system env credentials if custom credentials incomplete
    if not smtp_user or not smtp_password:
        smtp_user = (os.getenv('SMTP_USER') or '').strip()
        smtp_password = (os.getenv('SMTP_PASSWORD') or '').strip()
        use_custom = False

    sender_email = smtp_user or (os.getenv('SENDER_EMAIL') or '').strip() or 'no-reply@smartcivic.ai'
    app_base_url = os.getenv('APP_BASE_URL', 'http://127.0.0.1:5000').rstrip('/')

    print(f"\n============================================================")
    print(f"[EMAIL SERVICE] Preparing email notification to: {to_email}")
    try:
        print(f"Subject: {subject}")
    except UnicodeEncodeError:
        print(f"Subject: {subject.encode('ascii', errors='replace').decode('ascii')}")
    if smtp_user:
        print(f"Dispatching via Gmail Sender: {smtp_user} (Custom user credentials: {use_custom})")

    if not smtp_user or not smtp_password:
        print(f"[EMAIL SERVICE WARNING] No active Gmail SMTP credentials (user or .env).")
        print(f"[EMAIL SERVICE] Simulating email sending (Mock Log):")
        print(f"To: {to_email}")
        print(f"Content Summary: {text_content or 'HTML Complaint Notification'}")
        print(f"============================================================\n")
        return

    msg = MIMEMultipart('alternative')
    try:
        msg['Subject'] = subject
        msg['From'] = f"SmartCivic AI <{sender_email}>"
        msg['To'] = to_email

        if text_content:
            part1 = MIMEText(text_content, 'plain')
            msg.attach(part1)

        part2 = MIMEText(html_content, 'html')
        msg.attach(part2)

        with smtplib.SMTP(smtp_server, smtp_port, timeout=10) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(sender_email, [to_email], msg.as_string())

        print(f"[EMAIL SERVICE SUCCESS] Email sent successfully to {to_email} via {sender_email}")
        print(f"============================================================\n")
    except Exception as e:
        print(f"[EMAIL SERVICE ERROR] Primary SMTP send failed with {smtp_user}: {e}")
        # If custom credentials failed, attempt fallback to system env if available
        env_user = (os.getenv('SMTP_USER') or '').strip()
        env_pass = (os.getenv('SMTP_PASSWORD') or '').strip()
        if use_custom and env_user and env_pass and (env_user != smtp_user):
            print(f"[EMAIL SERVICE] Attempting fallback to system env credentials ({env_user})...")
            try:
                msg['From'] = f"SmartCivic AI <{env_user}>"
                with smtplib.SMTP(smtp_server, smtp_port, timeout=10) as server:
                    server.starttls()
                    server.login(env_user, env_pass)
                    server.sendmail(env_user, [to_email], msg.as_string())
                print(f"[EMAIL SERVICE SUCCESS] Fallback email sent successfully to {to_email}")
            except Exception as fallback_err:
                print(f"[EMAIL SERVICE ERROR] Fallback SMTP send failed: {fallback_err}")
        print(f"============================================================\n")

def send_welcome_email(user_dict, sender_gmail=None, sender_password=None):
    """
    Sends a welcome email upon user registration using their registered Gmail credentials.
    """
    to_email = user_dict.get('gmail')
    if not to_email:
        return

    name = user_dict.get('name', 'Citizen')
    role = user_dict.get('role', 'citizen').capitalize()
    app_base_url = os.getenv('APP_BASE_URL', 'http://127.0.0.1:5000').rstrip('/')

    subject = f"Welcome to SmartCivic AI, {name}!"

    text_body = (
        f"Welcome to SmartCivic AI, {name}!\n\n"
        f"Your account has been registered with role: {role}.\n"
        f"Registered Gmail: {to_email}\n\n"
        f"You can now submit issues, track status in real-time, and receive automated Gmail updates.\n"
        f"Portal URL: {app_base_url}\n\n"
        f"SmartCivic AI Team"
    )

    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f1f5f9; margin: 0; padding: 20px; color: #1e293b; }}
        .container {{ max-width: 600px; background: #ffffff; margin: 0 auto; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 15px rgba(0,0,0,0.08); }}
        .header {{ background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%); padding: 30px 25px; color: #ffffff; text-align: center; }}
        .header h1 {{ margin: 0; font-size: 24px; font-weight: 700; }}
        .content {{ padding: 30px 25px; }}
        .welcome-card {{ background: #eff6ff; border: 1px solid #bfdbfe; padding: 20px; border-radius: 8px; margin: 20px 0; }}
        .btn-portal {{ display: inline-block; background: #2563eb; color: #ffffff !important; text-decoration: none; padding: 14px 28px; border-radius: 8px; font-weight: 600; font-size: 15px; margin: 15px 0; text-align: center; }}
        .footer {{ background: #f8fafc; padding: 20px; text-align: center; font-size: 12px; color: #94a3b8; border-top: 1px solid #e2e8f0; }}
      </style>
    </head>
    <body>
      <div class="container">
        <div class="header">
          <h1>SmartCivic AI Registration</h1>
        </div>
        <div class="content">
          <h2>Welcome, {name}!</h2>
          <p>Thank you for signing up with SmartCivic AI. Your account is active and configured for real-time Gmail notifications.</p>
          
          <div class="welcome-card">
            <p style="margin: 5px 0;"><strong>Registered Gmail:</strong> {to_email}</p>
            <p style="margin: 5px 0;"><strong>Assigned Role:</strong> {role}</p>
          </div>

          <div style="text-align: center;">
            <a href="{app_base_url}" class="btn-portal" target="_blank">Access SmartCivic AI Portal &rarr;</a>
          </div>
        </div>
        <div class="footer">
          &copy; SmartCivic AI System.
        </div>
      </div>
    </body>
    </html>
    """

    # Pass sender credentials if specified, default to registered credentials
    s_gmail = sender_gmail or to_email
    s_pass = sender_password or user_dict.get('password')
    send_email_async(to_email, subject, html_body, text_body, sender_gmail=s_gmail, sender_password=s_pass)

def send_complaint_confirmation_email(to_email, complaint, sender_gmail=None, sender_password=None):
    """
    Sends a styled confirmation email with tracking link when a complaint is created.
    """
    if not to_email:
        return

    complaint_id = complaint.get('complaint_id', 'COMP-UNKNOWN')
    category = complaint.get('category', 'General')
    priority = complaint.get('priority', 'Medium')
    ward = complaint.get('ward', 'Ward 1')
    status = complaint.get('status', 'Submitted')
    description = complaint.get('description', '')
    app_base_url = os.getenv('APP_BASE_URL', 'http://127.0.0.1:5000').rstrip('/')
    tracking_link = f"{app_base_url}/?track={complaint_id}"

    subject = f"Complaint Received [{complaint_id}] - SmartCivic AI Tracking"

    text_body = (
        f"Thank you for reporting an issue to SmartCivic AI!\n\n"
        f"Complaint Tracking ID: {complaint_id}\n"
        f"Category: {category}\n"
        f"Priority: {priority}\n"
        f"Ward: {ward}\n"
        f"Status: {status}\n"
        f"Description: {description}\n\n"
        f"Track your complaint online here:\n"
        f"{tracking_link}\n\n"
        f"SmartCivic AI Team"
    )

    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f1f5f9; margin: 0; padding: 20px; color: #1e293b; }}
        .container {{ max-width: 600px; background: #ffffff; margin: 0 auto; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 15px rgba(0,0,0,0.08); }}
        .header {{ background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%); padding: 30px 25px; color: #ffffff; text-align: center; }}
        .header h1 {{ margin: 0; font-size: 24px; font-weight: 700; letter-spacing: 0.5px; }}
        .header p {{ margin: 8px 0 0; opacity: 0.9; font-size: 14px; }}
        .content {{ padding: 30px 25px; }}
        .badge {{ display: inline-block; background: #eff6ff; color: #2563eb; padding: 6px 14px; border-radius: 20px; font-weight: 600; font-size: 14px; margin-bottom: 15px; border: 1px solid #bfdbfe; }}
        .meta-table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        .meta-table td {{ padding: 10px 12px; border-bottom: 1px solid #e2e8f0; font-size: 14px; }}
        .meta-table td.label {{ font-weight: 600; color: #64748b; width: 35%; }}
        .meta-table td.value {{ color: #0f172a; font-weight: 500; }}
        .btn-track {{ display: inline-block; background: #2563eb; color: #ffffff !important; text-decoration: none; padding: 14px 28px; border-radius: 8px; font-weight: 600; font-size: 15px; margin: 20px 0 10px; text-align: center; box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3); }}
        .footer {{ background: #f8fafc; padding: 20px; text-align: center; font-size: 12px; color: #94a3b8; border-top: 1px solid #e2e8f0; }}
      </style>
    </head>
    <body>
      <div class="container">
        <div class="header">
          <h1>SmartCivic AI Notification</h1>
          <p>Complaint Filed & Registered</p>
        </div>
        <div class="content">
          <span class="badge">Tracking ID: {complaint_id}</span>
          <p style="font-size: 15px; line-height: 1.6;">Hello,</p>
          <p style="font-size: 15px; line-height: 1.6;">Thank you for submitting a civic complaint. Our AI system has logged your report and routed it to the designated ward authority.</p>
          
          <table class="meta-table">
            <tr>
              <td class="label">Complaint ID:</td>
              <td class="value"><strong>{complaint_id}</strong></td>
            </tr>
            <tr>
              <td class="label">Category:</td>
              <td class="value">{category}</td>
            </tr>
            <tr>
              <td class="label">Priority Level:</td>
              <td class="value">{priority}</td>
            </tr>
            <tr>
              <td class="label">Assigned Ward:</td>
              <td class="value">{ward}</td>
            </tr>
            <tr>
              <td class="label">Initial Status:</td>
              <td class="value"><span style="color: #2563eb; font-weight: 600;">{status}</span></td>
            </tr>
            <tr>
              <td class="label">Description:</td>
              <td class="value">{description}</td>
            </tr>
          </table>

          <div style="text-align: center;">
            <a href="{tracking_link}" class="btn-track" target="_blank">Track Complaint Status Live &rarr;</a>
          </div>

          <p style="font-size: 13px; color: #64748b; margin-top: 20px; text-align: center;">
            Direct URL: <a href="{tracking_link}" style="color: #2563eb;">{tracking_link}</a>
          </p>
        </div>
        <div class="footer">
          &copy; SmartCivic AI System. Automated email notification.
        </div>
      </div>
    </body>
    </html>
    """

    send_email_async(to_email, subject, html_body, text_body, sender_gmail=sender_gmail, sender_password=sender_password)

def send_complaint_status_update_email(to_email, complaint, notes=None, sender_gmail=None, sender_password=None):
    """
    Sends an email update to the citizen when complaint status changes (e.g. Assigned, Resolved).
    """
    if not to_email:
        return

    complaint_id = complaint.get('complaint_id', 'COMP-UNKNOWN')
    category = complaint.get('category', 'General')
    status = complaint.get('status', 'Updated')
    assigned_to_name = complaint.get('assigned_to_name')
    ward = complaint.get('ward', 'Ward 1')
    app_base_url = os.getenv('APP_BASE_URL', 'http://127.0.0.1:5000').rstrip('/')
    tracking_link = f"{app_base_url}/?track={complaint_id}"

    subject = f"Complaint Status Updated [{status}] - {complaint_id}"

    status_color = "#2563eb"
    if status == "Resolved":
        status_color = "#16a34a"
    elif status == "In Progress":
        status_color = "#d97706"
    elif status == "Assigned":
        status_color = "#4f46e5"

    text_body = (
        f"Your Complaint [{complaint_id}] status has been updated to: {status}.\n\n"
        f"Complaint ID: {complaint_id}\n"
        f"New Status: {status}\n"
        f"Assigned Worker: {assigned_to_name or 'Ward Team'}\n"
        f"Notes / Resolution Details: {notes or 'No additional notes'}\n\n"
        f"Track full timeline details online:\n"
        f"{tracking_link}\n\n"
        f"SmartCivic AI Team"
    )

    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f1f5f9; margin: 0; padding: 20px; color: #1e293b; }}
        .container {{ max-width: 600px; background: #ffffff; margin: 0 auto; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 15px rgba(0,0,0,0.08); }}
        .header {{ background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); padding: 25px; color: #ffffff; text-align: center; }}
        .header h1 {{ margin: 0; font-size: 22px; font-weight: 700; }}
        .content {{ padding: 30px 25px; }}
        .status-card {{ background: #f8fafc; border-left: 5px solid {status_color}; padding: 15px 20px; border-radius: 6px; margin: 20px 0; }}
        .status-title {{ font-size: 13px; text-transform: uppercase; color: #64748b; font-weight: 700; margin-bottom: 5px; }}
        .status-value {{ font-size: 20px; font-weight: 700; color: {status_color}; }}
        .btn-track {{ display: inline-block; background: #2563eb; color: #ffffff !important; text-decoration: none; padding: 12px 24px; border-radius: 8px; font-weight: 600; font-size: 14px; margin: 20px 0; text-align: center; }}
        .footer {{ background: #f8fafc; padding: 15px; text-align: center; font-size: 12px; color: #94a3b8; border-top: 1px solid #e2e8f0; }}
      </style>
    </head>
    <body>
      <div class="container">
        <div class="header">
          <h1>SmartCivic AI Update</h1>
        </div>
        <div class="content">
          <p style="font-size: 15px;">Hello,</p>
          <p style="font-size: 15px;">There is an update on your reported issue <strong>{complaint_id}</strong>.</p>
          
          <div class="status-card">
            <div class="status-title">Current Complaint Status</div>
            <div class="status-value">{status}</div>
          </div>

          <table style="width:100%; font-size:14px; border-collapse:collapse; margin:15px 0;">
            <tr>
              <td style="padding:8px 0; color:#64748b; font-weight:600;">Category:</td>
              <td style="padding:8px 0; color:#0f172a;">{category}</td>
            </tr>
            <tr>
              <td style="padding:8px 0; color:#64748b; font-weight:600;">Ward:</td>
              <td style="padding:8px 0; color:#0f172a;">{ward}</td>
            </tr>
            {f'<tr><td style="padding:8px 0; color:#64748b; font-weight:600;">Assigned To:</td><td style="padding:8px 0; color:#0f172a;">{assigned_to_name}</td></tr>' if assigned_to_name else ''}
            {f'<tr><td style="padding:8px 0; color:#64748b; font-weight:600;">Notes:</td><td style="padding:8px 0; color:#0f172a;">{notes}</td></tr>' if notes else ''}
          </table>

          <div style="text-align: center;">
            <a href="{tracking_link}" class="btn-track" target="_blank">View Updated Complaint Timeline &rarr;</a>
          </div>
        </div>
        <div class="footer">
          &copy; SmartCivic AI System. Automated status update notification.
        </div>
      </div>
    </body>
    </html>
    """

    send_email_async(to_email, subject, html_body, text_body, sender_gmail=sender_gmail, sender_password=sender_password)

def send_geotag_authority_alert(to_email, complaint, sender_gmail=None, sender_password=None):
    """
    Sends an automated Geotag GPS dispatch alert to Ward Authority.
    """
    if not to_email:
        return

    complaint_id = complaint.get('complaint_id', 'COMP-UNKNOWN')
    category = complaint.get('category', 'General')
    priority = complaint.get('priority', 'High')
    ward = complaint.get('ward', 'General')
    lat = complaint.get('latitude')
    lng = complaint.get('longitude')
    desc = complaint.get('description', '')
    gmaps_url = f"https://www.google.com/maps?q={lat},{lng}"
    app_base_url = os.getenv('APP_BASE_URL', 'http://127.0.0.1:5000').rstrip('/')

    subject = f"🚨 GEOTAG ALERT [{complaint_id}]: New {category.upper()} in {ward}"

    text_body = (
        f"GEOTAG CIVIC ALERT - SmartCivic AI\n\n"
        f"A geotagged photo issue has been received and routed to your ward ({ward}).\n"
        f"Complaint ID: {complaint_id}\n"
        f"Category: {category}\n"
        f"Priority: {priority}\n"
        f"GPS Coordinates: Lat {lat}, Lng {lng}\n"
        f"Google Maps Location: {gmaps_url}\n"
        f"Description: {desc}\n\n"
        f"SmartCivic AI Admin Portal: {app_base_url}\n"
    )

    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f1f5f9; margin: 0; padding: 20px; color: #1e293b; }}
        .container {{ max-width: 600px; background: #ffffff; margin: 0 auto; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 15px rgba(0,0,0,0.08); }}
        .header {{ background: linear-gradient(135deg, #dc2626 0%, #991b1b 100%); padding: 25px; color: #ffffff; text-align: center; }}
        .header h1 {{ margin: 0; font-size: 22px; font-weight: 700; }}
        .content {{ padding: 30px 25px; }}
        .gps-box {{ background: #fef2f2; border: 1px solid #fecaca; border-left: 5px solid #ef4444; padding: 15px 20px; border-radius: 8px; margin: 20px 0; }}
        .gps-coords {{ font-size: 18px; font-weight: 700; color: #b91c1c; font-family: monospace; }}
        .btn-gmaps {{ display: inline-block; background: #dc2626; color: #ffffff !important; text-decoration: none; padding: 12px 24px; border-radius: 8px; font-weight: 600; font-size: 14px; margin: 15px 0; text-align: center; }}
        .footer {{ background: #f8fafc; padding: 15px; text-align: center; font-size: 12px; color: #94a3b8; border-top: 1px solid #e2e8f0; }}
      </style>
    </head>
    <body>
      <div class="container">
        <div class="header">
          <h1>🚨 GEOTAG CIVIC ALERT</h1>
          <p>Automated Authority Dispatch Notice</p>
        </div>
        <div class="content">
          <p style="font-size: 15px;">Hello Authority Officer,</p>
          <p style="font-size: 15px;">A new geotag-verified issue <strong>{complaint_id}</strong> has been logged in <strong>{ward}</strong>.</p>
          
          <div class="gps-box">
            <div style="font-size:12px; text-transform:uppercase; color:#991b1b; font-weight:700;">Verified GPS Location</div>
            <div class="gps-coords">Lat: {lat}, Lng: {lng}</div>
          </div>

          <table style="width:100%; font-size:14px; border-collapse:collapse; margin:15px 0;">
            <tr><td style="padding:6px 0; color:#64748b; font-weight:600;">Category:</td><td style="padding:6px 0; color:#0f172a;">{category}</td></tr>
            <tr><td style="padding:6px 0; color:#64748b; font-weight:600;">Priority:</td><td style="padding:6px 0; color:#dc2626; font-weight:700;">{priority}</td></tr>
            <tr><td style="padding:6px 0; color:#64748b; font-weight:600;">Ward:</td><td style="padding:6px 0; color:#0f172a;">{ward}</td></tr>
            <tr><td style="padding:6px 0; color:#64748b; font-weight:600;">Description:</td><td style="padding:6px 0; color:#0f172a;">{desc}</td></tr>
          </table>

          <div style="text-align: center;">
            <a href="{gmaps_url}" class="btn-gmaps" target="_blank">📍 Open Location in Google Maps &rarr;</a>
          </div>
        </div>
        <div class="footer">
          &copy; SmartCivic AI Authority Dispatch System.
        </div>
      </div>
    </body>
    </html>
    """

    send_email_async(to_email, subject, html_body, text_body, sender_gmail=sender_gmail, sender_password=sender_password)

def send_geotag_worker_assignment(to_email, complaint, sender_gmail=None, sender_password=None):
    """
    Sends an automated Geotag GPS dispatch & route assignment alert to Worker.
    """
    if not to_email:
        return

    complaint_id = complaint.get('complaint_id', 'COMP-UNKNOWN')
    category = complaint.get('category', 'General')
    priority = complaint.get('priority', 'High')
    ward = complaint.get('ward', 'General')
    lat = complaint.get('latitude')
    lng = complaint.get('longitude')
    desc = complaint.get('description', '')
    gmaps_nav = f"https://www.google.com/maps/dir/?api=1&destination={lat},{lng}"
    app_base_url = os.getenv('APP_BASE_URL', 'http://127.0.0.1:5000').rstrip('/')

    subject = f"🛠️ WORK DISPATCH [{complaint_id}]: {category.upper()} in {ward}"

    text_body = (
        f"WORK DISPATCH NOTICE - SmartCivic AI\n\n"
        f"You have been assigned to resolve a geotagged civic issue in {ward}.\n"
        f"Complaint ID: {complaint_id}\n"
        f"Category: {category}\n"
        f"GPS Coordinates: Lat {lat}, Lng {lng}\n"
        f"Google Maps Navigation: {gmaps_nav}\n"
        f"Task Description: {desc}\n\n"
        f"Worker Portal: {app_base_url}\n"
    )

    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f1f5f9; margin: 0; padding: 20px; color: #1e293b; }}
        .container {{ max-width: 600px; background: #ffffff; margin: 0 auto; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 15px rgba(0,0,0,0.08); }}
        .header {{ background: linear-gradient(135deg, #16a34a 0%, #15803d 100%); padding: 25px; color: #ffffff; text-align: center; }}
        .header h1 {{ margin: 0; font-size: 22px; font-weight: 700; }}
        .content {{ padding: 30px 25px; }}
        .gps-box {{ background: #f0fdf4; border: 1px solid #bbf7d0; border-left: 5px solid #16a34a; padding: 15px 20px; border-radius: 8px; margin: 20px 0; }}
        .gps-coords {{ font-size: 18px; font-weight: 700; color: #15803d; font-family: monospace; }}
        .btn-nav {{ display: inline-block; background: #16a34a; color: #ffffff !important; text-decoration: none; padding: 14px 28px; border-radius: 8px; font-weight: 600; font-size: 15px; margin: 15px 0; text-align: center; }}
        .footer {{ background: #f8fafc; padding: 15px; text-align: center; font-size: 12px; color: #94a3b8; border-top: 1px solid #e2e8f0; }}
      </style>
    </head>
    <body>
      <div class="container">
        <div class="header">
          <h1>🛠️ WORK DISPATCH ASSIGNMENT</h1>
          <p>Automated GPS Location Dispatch</p>
        </div>
        <div class="content">
          <p style="font-size: 15px;">Hello Field Worker,</p>
          <p style="font-size: 15px;">You have been assigned to resolve complaint <strong>{complaint_id}</strong> located in <strong>{ward}</strong>.</p>
          
          <div class="gps-box">
            <div style="font-size:12px; text-transform:uppercase; color:#15803d; font-weight:700;">Exact Field GPS Target</div>
            <div class="gps-coords">Lat: {lat}, Lng: {lng}</div>
          </div>

          <table style="width:100%; font-size:14px; border-collapse:collapse; margin:15px 0;">
            <tr><td style="padding:6px 0; color:#64748b; font-weight:600;">Category:</td><td style="padding:6px 0; color:#0f172a;">{category}</td></tr>
            <tr><td style="padding:6px 0; color:#64748b; font-weight:600;">Priority:</td><td style="padding:6px 0; color:#0f172a; font-weight:700;">{priority}</td></tr>
            <tr><td style="padding:6px 0; color:#64748b; font-weight:600;">Description:</td><td style="padding:6px 0; color:#0f172a;">{desc}</td></tr>
          </table>

          <div style="text-align: center;">
            <a href="{gmaps_nav}" class="btn-nav" target="_blank">🗺️ Start GPS Navigation to Site &rarr;</a>
          </div>
        </div>
        <div class="footer">
          &copy; SmartCivic AI Worker Dispatch System.
        </div>
      </div>
    </body>
    </html>
    """

    send_email_async(to_email, subject, html_body, text_body, sender_gmail=sender_gmail, sender_password=sender_password)


def send_authority_pending_approval_email(user_dict):
    """
    Notifies an authority applicant that their registration is awaiting Municipal Admin approval.
    """
    to_email = user_dict.get('gmail')
    if not to_email:
        return
    name = user_dict.get('name', 'Officer')
    ward = (user_dict.get('ward') or 'general').replace('_', ' ').title()
    app_base_url = os.getenv('APP_BASE_URL', 'http://127.0.0.1:5000').rstrip('/')

    subject = f"🏛️ Authority Application Received - SmartCivic AI ({ward})"

    text_body = (
        f"Hello {name},\n\n"
        f"Your registration application for Civic Authority access in {ward} has been submitted.\n"
        f"Status: PENDING MUNICIPAL ADMIN REVIEW\n\n"
        f"Once the Municipal Administrator approves your credentials, you will receive your official Secret Authorization Key via this Gmail address.\n\n"
        f"SmartCivic AI Municipal Governance Team"
    )

    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #0f172a; margin: 0; padding: 20px; color: #e2e8f0; }}
        .container {{ max-width: 600px; background: #1e293b; margin: 0 auto; border-radius: 12px; overflow: hidden; box-shadow: 0 10px 25px rgba(0,0,0,0.3); border: 1px solid #334155; }}
        .header {{ background: linear-gradient(135deg, #1e1b4b 0%, #312e81 100%); padding: 30px 25px; color: #ffffff; text-align: center; border-bottom: 2px solid #4f46e5; }}
        .header h1 {{ margin: 0; font-size: 22px; font-weight: 700; letter-spacing: 0.5px; }}
        .content {{ padding: 30px 25px; }}
        .status-badge {{ display: inline-block; background: #fef3c7; color: #92400e; padding: 6px 14px; border-radius: 20px; font-weight: 700; font-size: 13px; margin: 15px 0; }}
        .info-box {{ background: #0f172a; border-left: 4px solid #6366f1; padding: 15px 20px; border-radius: 6px; margin: 20px 0; }}
        .footer {{ background: #0b0f19; padding: 18px; text-align: center; font-size: 12px; color: #64748b; border-top: 1px solid #1e293b; }}
      </style>
    </head>
    <body>
      <div class="container">
        <div class="header">
          <h1>🏛️ SMARTCIVIC AI GOVERNANCE</h1>
          <p style="margin: 6px 0 0 0; color: #c7d2fe; font-size: 14px;">Authority Application Received</p>
        </div>
        <div class="content">
          <p style="font-size: 16px; margin-top: 0;">Hello <strong>{name}</strong>,</p>
          <p style="font-size: 14px; line-height: 1.6; color: #94a3b8;">
            Your registration as a <strong>Municipal Authority Officer</strong> for <strong>{ward}</strong> has been received and logged into the governance portal.
          </p>

          <div style="text-align: center;">
            <div class="status-badge">⏳ STATUS: PENDING ADMIN APPROVAL</div>
          </div>

          <div class="info-box">
            <div style="font-size: 13px; color: #818cf8; font-weight: 600; margin-bottom: 4px;">Next Steps:</div>
            <div style="font-size: 14px; color: #cbd5e1; line-height: 1.5;">
              The Chief Municipal Administrator will verify your ward designation. Once approved, you will receive your <strong>Secret Access Key</strong> to log in.
            </div>
          </div>

          <p style="font-size: 13px; color: #64748b; margin-top: 25px;">
            If you did not initiate this registration, please contact municipal cybersecurity support.
          </p>
        </div>
        <div class="footer">
          &copy; SmartCivic AI Municipal Governance Authority &bull; System ID: {user_dict.get('id', 'N/A')}
        </div>
      </div>
    </body>
    </html>
    """
    send_email_async(to_email, subject, html_body, text_body)


def send_authority_approval_email(user_dict, secret_key):
    """
    Sends the official Approval Confirmation and Secret Access Key to the approved authority.
    """
    to_email = user_dict.get('gmail')
    if not to_email:
        return
    name = user_dict.get('name', 'Officer')
    ward = (user_dict.get('ward') or 'general').replace('_', ' ').title()
    app_base_url = os.getenv('APP_BASE_URL', 'http://127.0.0.1:5000').rstrip('/')

    subject = f"🔐 Official Authority Access Approved - Secret Key Enclosed [SmartCivic AI]"

    text_body = (
        f"Congratulations {name},\n\n"
        f"Your Municipal Authority account for {ward} has been officially APPROVED by the Administrator.\n\n"
        f"YOUR SECRET ACCESS KEY: {secret_key}\n\n"
        f"How to log in:\n"
        f"1. Navigate to: {app_base_url}\n"
        f"2. Choose role: Authority\n"
        f"3. Enter your Gmail: {to_email}\n"
        f"4. Enter your Password and Secret Access Key ({secret_key})\n\n"
        f"IMPORTANT SECURITY NOTICE: Do NOT share this key with anyone. This is your permanent municipal officer authorization code.\n\n"
        f"SmartCivic AI Administration"
    )

    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #090d16; margin: 0; padding: 20px; color: #e2e8f0; }}
        .container {{ max-width: 600px; background: #131c2e; margin: 0 auto; border-radius: 14px; overflow: hidden; box-shadow: 0 12px 35px rgba(0,0,0,0.4); border: 1px solid #1e293b; }}
        .header {{ background: linear-gradient(135deg, #047857 0%, #065f46 100%); padding: 32px 25px; color: #ffffff; text-align: center; border-bottom: 2px solid #10b981; }}
        .header h1 {{ margin: 0; font-size: 24px; font-weight: 800; letter-spacing: 0.5px; }}
        .content {{ padding: 32px 28px; }}
        .key-card {{ background: linear-gradient(145deg, #0f172a, #1e293b); border: 2px dashed #10b981; border-radius: 10px; padding: 22px; margin: 24px 0; text-align: center; }}
        .key-label {{ font-size: 12px; text-transform: uppercase; letter-spacing: 1.5px; color: #34d399; font-weight: 700; margin-bottom: 8px; }}
        .key-value {{ font-family: 'Courier New', monospace; font-size: 26px; font-weight: 800; color: #ffffff; letter-spacing: 3px; background: #022c22; padding: 10px 20px; border-radius: 6px; display: inline-block; border: 1px solid #059669; }}
        .btn-login {{ display: inline-block; background: linear-gradient(135deg, #10b981 0%, #059669 100%); color: #ffffff !important; text-decoration: none; padding: 14px 32px; border-radius: 8px; font-weight: 700; font-size: 15px; margin: 20px 0; text-align: center; box-shadow: 0 4px 15px rgba(16, 185, 129, 0.3); }}
        .security-alert {{ background: #451a03; border-left: 4px solid #f59e0b; padding: 14px 18px; border-radius: 6px; font-size: 13px; color: #fde68a; margin: 20px 0; line-height: 1.5; }}
        .footer {{ background: #090d16; padding: 18px; text-align: center; font-size: 12px; color: #64748b; border-top: 1px solid #1e293b; }}
      </style>
    </head>
    <body>
      <div class="container">
        <div class="header">
          <h1>🛡️ ACCESS GRANTED &bull; AUTHORITY</h1>
          <p style="margin: 6px 0 0 0; color: #a7f3d0; font-size: 14px;">SmartCivic AI &bull; {ward}</p>
        </div>
        <div class="content">
          <p style="font-size: 16px; margin-top: 0;">Welcome, <strong>{name}</strong>!</p>
          <p style="font-size: 14px; line-height: 1.6; color: #94a3b8;">
            Your registration as an authorized municipal supervisor for <strong>{ward}</strong> has been officially approved. You are now authorized to manage ward operations, resolve escalations, and dispatch field crews.
          </p>

          <div class="key-card">
            <div class="key-label">Your Permanent Secret Access Key</div>
            <div class="key-value">{secret_key}</div>
            <div style="font-size: 12px; color: #94a3b8; margin-top: 10px;">Use this key alongside your Gmail and Password whenever you log in.</div>
          </div>

          <div class="security-alert">
            <strong>🔒 Security Protocol:</strong> Keep this key secure and confidential. Municipal audit logs record all actions performed with this key.
          </div>

          <div style="text-align: center;">
            <a href="{app_base_url}" class="btn-login" target="_blank">🚀 Log In to Authority Portal &rarr;</a>
          </div>
        </div>
        <div class="footer">
          &copy; SmartCivic AI Municipal Governance Authority &bull; System ID: {user_dict.get('id', 'N/A')}
        </div>
      </div>
    </body>
    </html>
    """
    send_email_async(to_email, subject, html_body, text_body)


def send_authority_key_regenerated_email(user_dict, secret_key):
    """
    Sends the newly regenerated Secret Access Key when reset by the Admin.
    """
    to_email = user_dict.get('gmail')
    if not to_email:
        return
    name = user_dict.get('name', 'Officer')
    ward = (user_dict.get('ward') or 'general').replace('_', ' ').title()
    app_base_url = os.getenv('APP_BASE_URL', 'http://127.0.0.1:5000').rstrip('/')

    subject = f"🔄 Secret Access Key Regenerated - SmartCivic AI ({ward})"

    text_body = (
        f"Hello {name},\n\n"
        f"Your Secret Access Key for {ward} has been REGENERATED by the Municipal Administrator.\n\n"
        f"NEW SECRET ACCESS KEY: {secret_key}\n\n"
        f"Your previous key has been deactivated. Please use this new key for all future logins.\n"
        f"Portal: {app_base_url}\n\n"
        f"SmartCivic AI Administration"
    )

    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #090d16; margin: 0; padding: 20px; color: #e2e8f0; }}
        .container {{ max-width: 600px; background: #131c2e; margin: 0 auto; border-radius: 14px; overflow: hidden; box-shadow: 0 12px 35px rgba(0,0,0,0.4); border: 1px solid #1e293b; }}
        .header {{ background: linear-gradient(135deg, #4338ca 0%, #3730a3 100%); padding: 30px 25px; color: #ffffff; text-align: center; border-bottom: 2px solid #6366f1; }}
        .header h1 {{ margin: 0; font-size: 22px; font-weight: 800; }}
        .content {{ padding: 30px 28px; }}
        .key-card {{ background: linear-gradient(145deg, #0f172a, #1e293b); border: 2px dashed #6366f1; border-radius: 10px; padding: 20px; margin: 20px 0; text-align: center; }}
        .key-value {{ font-family: 'Courier New', monospace; font-size: 24px; font-weight: 800; color: #a5b4fc; letter-spacing: 3px; background: #1e1b4b; padding: 10px 18px; border-radius: 6px; display: inline-block; border: 1px solid #4f46e5; }}
        .footer {{ background: #090d16; padding: 18px; text-align: center; font-size: 12px; color: #64748b; border-top: 1px solid #1e293b; }}
      </style>
    </head>
    <body>
      <div class="container">
        <div class="header">
          <h1>🔄 SECRET KEY REGENERATED</h1>
          <p style="margin: 6px 0 0 0; color: #c7d2fe; font-size: 14px;">SmartCivic AI &bull; {ward}</p>
        </div>
        <div class="content">
          <p style="font-size: 16px; margin-top: 0;">Hello <strong>{name}</strong>,</p>
          <p style="font-size: 14px; line-height: 1.6; color: #94a3b8;">
            The Municipal Administrator has issued a <strong>new Secret Access Key</strong> for your account. All previous keys have been permanently revoked.
          </p>

          <div class="key-card">
            <div style="font-size: 12px; text-transform: uppercase; color: #818cf8; font-weight: 700; margin-bottom: 8px;">Your New Secret Access Key</div>
            <div class="key-value">{secret_key}</div>
          </div>

          <p style="font-size: 14px; color: #94a3b8;">
            Use this key for all future logins on the SmartCivic AI Authority Portal.
          </p>
        </div>
        <div class="footer">
          &copy; SmartCivic AI Municipal Governance Authority &bull; System ID: {user_dict.get('id', 'N/A')}
        </div>
      </div>
    </body>
    </html>
    """
    send_email_async(to_email, subject, html_body, text_body)


def send_authority_rejection_email(user_dict, reason=None):
    """
    Notifies applicant that authority registration was declined.
    """
    to_email = user_dict.get('gmail')
    if not to_email:
        return
    name = user_dict.get('name', 'Applicant')
    ward = (user_dict.get('ward') or 'general').replace('_', ' ').title()

    subject = f"SmartCivic AI Authority Application Update ({ward})"
    text_body = f"Hello {name},\n\nYour application for Municipal Authority status in {ward} was not approved by the Administrator.\nReason: {reason or 'Verification of official municipal credentials could not be completed.'}\n\nSmartCivic AI Team"
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"></head>
    <body style="font-family: sans-serif; background: #0f172a; padding: 20px; color: #e2e8f0;">
      <div style="max-width: 550px; background: #1e293b; margin: 0 auto; padding: 25px; border-radius: 10px; border: 1px solid #334155;">
        <h2 style="color: #ef4444; margin-top: 0;">Authority Registration Update</h2>
        <p>Hello <strong>{name}</strong>,</p>
        <p style="color: #94a3b8;">Your registration request for Authority access in <strong>{ward}</strong> was reviewed and declined by the municipal administration.</p>
        <div style="background: #450a0a; border-left: 4px solid #ef4444; padding: 12px 15px; border-radius: 4px; color: #fca5a5; font-size: 13px;">
          <strong>Note:</strong> {reason or 'Official municipal authority credentials could not be verified.'}
        </div>
        <p style="color: #64748b; font-size: 12px; margin-top: 20px;">You may still participate as a registered citizen on the platform.</p>
      </div>
    </body>
    </html>
    """
    send_email_async(to_email, subject, html_body, text_body)

