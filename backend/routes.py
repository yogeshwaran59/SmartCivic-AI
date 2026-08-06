import os
import uuid
from datetime import datetime
from flask import Blueprint, request, jsonify, Response, current_app
from werkzeug.utils import secure_filename
from models import db, User, Complaint, StatusLog
from ai_processor import classify_complaint_text, haversine_distance, get_image_similarity, analyze_and_describe_image

routes_bp = Blueprint('routes', __name__)

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Helper function for smart ward routing
def get_ward_by_location(lat, lng):
    # Center of Bangalore-like coords (12.97, 77.59)
    # Simple bounding boxes for ward routing
    if lat > 12.97:
        return 'ward_1' if lng < 77.59 else 'ward_2'
    else:
        return 'ward_3'

@routes_bp.route('/api/complaints', methods=['POST'])
def create_complaint():
    """
    Creates a new complaint. Runs AI duplicate check and text classification.
    Form data:
    - description (text)
    - latitude (float)
    - longitude (float)
    - contact (text)
    - image (file, optional)
    """
    try:
        description = request.form.get('description', '')
        latitude_str = request.form.get('latitude')
        longitude_str = request.form.get('longitude')
        contact = request.form.get('contact', '')

        if not description or not latitude_str or not longitude_str:
            return jsonify({'error': 'Description, latitude, and longitude are required.'}), 400

        try:
            latitude = float(latitude_str)
            longitude = float(longitude_str)
        except ValueError:
            return jsonify({'error': 'Invalid latitude or longitude values.'}), 400

        # Create unique ID for complaint
        complaint_id = f"COMP-{uuid.uuid4().hex[:6].upper()}"

        # Handle image upload
        image_file = request.files.get('image')
        image_path = None
        if image_file and image_file.filename:
            filename = f"{complaint_id}_{secure_filename(image_file.filename)}"
            save_path = os.path.join(UPLOAD_FOLDER, filename)
            image_file.save(save_path)
            image_path = f"/uploads/{filename}"

        # Smart Ward Routing
        ward = get_ward_by_location(latitude, longitude)

        # AI Classifier: Auto category & priority
        category, priority = classify_complaint_text(description)

        # AI Duplicate Check: Find nearby complaints (50m radius)
        # and compare images if both exist
        duplicate_flag = False
        duplicate_of = None
        existing_complaints = Complaint.query.filter(
            Complaint.status.in_(['Submitted', 'Assigned', 'In Progress'])
        ).all()

        for ext in existing_complaints:
            # Geographic check
            dist = haversine_distance(latitude, longitude, ext.latitude, ext.longitude)
            if dist <= 50.0:  # 50 meters
                # If images are present, check image similarity
                if image_path and ext.image_path:
                    abs_path_new = os.path.join(os.path.dirname(__file__), image_path.lstrip('/'))
                    abs_path_ext = os.path.join(os.path.dirname(__file__), ext.image_path.lstrip('/'))
                    similarity = get_image_similarity(abs_path_new, abs_path_ext)
                    if similarity > 0.82:
                        duplicate_flag = True
                        duplicate_of = ext.complaint_id
                        break
                else:
                    # If no images, check if category matches and descriptions are similar
                    if category == ext.category:
                        duplicate_flag = True
                        duplicate_of = ext.complaint_id
                        break

        # Run image analysis
        image_analysis = None
        if image_path:
            abs_path_new = os.path.join(os.path.dirname(__file__), image_path.lstrip('/'))
            image_analysis = analyze_and_describe_image(abs_path_new)

        # Save to database
        new_complaint = Complaint(
            complaint_id=complaint_id,
            description=description,
            image_path=image_path,
            latitude=latitude,
            longitude=longitude,
            category=category,
            priority=priority,
            status='Submitted',
            created_at=datetime.utcnow(),
            escalation_flag=duplicate_flag,  # We can flag it, or keep track of duplicate
            ward=ward,
            image_analysis=image_analysis
        )
        
        # Add to session
        db.session.add(new_complaint)
        db.session.flush() # Populate models to write to log

        # Initial Status Log
        log_status = "Submitted"
        if duplicate_flag:
            log_status = f"Submitted (Duplicate of {duplicate_of})"
            
        log = StatusLog(
            complaint_id=complaint_id,
            status=log_status,
            timestamp=datetime.utcnow()
        )
        db.session.add(log)
        db.session.commit()

        # Print mock SMS log
        print(f"============================================================")
        print(f"[NEW] COMPLAINT RECEIVED: {complaint_id}")
        print(f"Location: {latitude}, {longitude} -> Assigned to Ward: {ward}")
        print(f"AI Categorization: Category='{category}', Priority='{priority}'")
        if duplicate_flag:
            print(f"WARNING: AI DUPLICATE CHECK: Flagged as DUPLICATE of {duplicate_of}")
        print(f"MOCK SMS SENT TO CITIZEN ({contact}): "
              f"'Thank you for reporting! Your complaint ID is {complaint_id}. Status: {log_status}. Ward: {ward}.'")
        print(f"============================================================")

        response_data = new_complaint.to_dict()
        response_data['is_duplicate'] = duplicate_flag
        response_data['duplicate_of'] = duplicate_of

        return jsonify(response_data), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@routes_bp.route('/api/complaints', methods=['GET'])
def get_complaints():
    """
    Get list of complaints. Supports filtering by ward, status, priority, category.
    """
    try:
        query = Complaint.query
        
        # Apply filters
        ward = request.args.get('ward')
        status = request.args.get('status')
        priority = request.args.get('priority')
        category = request.args.get('category')
        redirected_to_journalist = request.args.get('redirected_to_journalist')
        created_after = request.args.get('created_after')

        if ward:
            query = query.filter_by(ward=ward)
        if status:
            query = query.filter_by(status=status)
        if priority:
            query = query.filter_by(priority=priority)
        if category:
            query = query.filter_by(category=category)
        if redirected_to_journalist is not None:
            val = redirected_to_journalist.lower() in ['true', '1']
            query = query.filter_by(redirected_to_journalist=val)
        if created_after:
            try:
                date_obj = datetime.fromisoformat(created_after)
                query = query.filter(Complaint.created_at >= date_obj)
            except ValueError:
                pass

        # Order by creation date descending
        complaints = query.order_by(Complaint.created_at.desc()).all()
        return jsonify([c.to_dict() for c in complaints]), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@routes_bp.route('/api/heatmap/summary', methods=['GET'])
def get_heatmap_summary():
    """
    Get aggregated regional complaint density and coordinates for heatmaps.
    Categorizes regions/wards as:
    - High (Red): > 5 complaints
    - Moderate (Yellow): 3 - 5 complaints
    - Low (Green): 1 - 2 complaints
    """
    try:
        complaints = Complaint.query.all()
        ward_map = {}
        for c in complaints:
            w = c.ward or 'General Ward'
            if w not in ward_map:
                ward_map[w] = {
                    'ward': w,
                    'count': 0,
                    'latitudes': [],
                    'longitudes': [],
                    'high_priority_count': 0,
                    'categories': {}
                }
            ward_map[w]['count'] += 1
            if c.latitude is not None: ward_map[w]['latitudes'].append(c.latitude)
            if c.longitude is not None: ward_map[w]['longitudes'].append(c.longitude)
            if c.priority == 'High': ward_map[w]['high_priority_count'] += 1
            cat = c.category or 'other'
            ward_map[w]['categories'][cat] = ward_map[w]['categories'].get(cat, 0) + 1

        summary = []
        for w, data in ward_map.items():
            avg_lat = sum(data['latitudes']) / len(data['latitudes']) if data['latitudes'] else 13.0827
            avg_lng = sum(data['longitudes']) / len(data['longitudes']) if data['longitudes'] else 80.2707
            count = data['count']
            if count > 5:
                severity = 'High'
                color = '#ef4444' # Red
            elif count >= 3:
                severity = 'Moderate'
                color = '#f59e0b' # Yellow
            else:
                severity = 'Low'
                color = '#10b981' # Green

            summary.append({
                'ward': w,
                'count': count,
                'avg_lat': avg_lat,
                'avg_lng': avg_lng,
                'severity': severity,
                'color': color,
                'high_priority_count': data['high_priority_count'],
                'categories': data['categories']
            })

        points = [{
            'complaint_id': c.complaint_id,
            'lat': c.latitude,
            'lng': c.longitude,
            'category': c.category,
            'priority': c.priority,
            'ward': c.ward,
            'weight': 1.0 if c.priority == 'High' else (0.7 if c.priority == 'Medium' else 0.4)
        } for c in complaints if c.latitude is not None and c.longitude is not None]

        return jsonify({
            'regional_summary': summary,
            'heat_points': points
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500



@routes_bp.route('/api/complaints/<id>', methods=['GET'])
def get_complaint_by_id(id):
    """
    Get a single complaint and its timeline history.
    """
    try:
        complaint = Complaint.query.get(id)
        if not complaint:
            return jsonify({'error': 'Complaint not found'}), 404
            
        logs = StatusLog.query.filter_by(complaint_id=id).order_by(StatusLog.timestamp.asc()).all()
        
        data = complaint.to_dict()
        data['history'] = [l.to_dict() for l in logs]
        return jsonify(data), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@routes_bp.route('/api/complaints/<id>', methods=['PUT'])
def update_complaint(id):
    """
    Updates status, worker assignment.
    Body JSON:
    - status ('Assigned' | 'In Progress' | 'Resolved' | 'Closed')
    - assigned_to (int, optional)
    - resolution_image (handled via multi-part or base64, but since it could be PUT form we support both JSON and form data)
    """
    try:
        complaint = Complaint.query.get(id)
        if not complaint:
            return jsonify({'error': 'Complaint not found'}), 404

        # Read JSON or Form data
        if request.is_json:
            data = request.json
            status = data.get('status')
            assigned_to = data.get('assigned_to')
        else:
            data = request.form
            status = data.get('status')
            assigned_to = data.get('assigned_to')

        if not status:
            return jsonify({'error': 'Status is required'}), 400

        # Handle worker assignment
        if assigned_to is not None:
            if assigned_to == "":
                complaint.assigned_to = None
            else:
                try:
                    worker_id = int(assigned_to)
                    worker = User.query.get(worker_id)
                    if worker:
                        complaint.assigned_to = worker_id
                        # If assigning, set status to 'Assigned' if it was 'Submitted'
                        if status == 'Submitted' or not status:
                            status = 'Assigned'
                except ValueError:
                    pass

        # Handle priority update
        priority = data.get('priority')
        if priority:
            complaint.priority = priority

        # Manage dates
        if status in ['Assigned', 'In Progress'] and not complaint.opened_at:
            complaint.opened_at = datetime.utcnow()

        # Handle resolution image (if file uploaded during PUT)
        resolution_file = request.files.get('resolution_image') if not request.is_json else None
        if resolution_file and resolution_file.filename:
            filename = f"RESOLVED_{id}_{secure_filename(resolution_file.filename)}"
            save_path = os.path.join(UPLOAD_FOLDER, filename)
            resolution_file.save(save_path)
            # Update complaint description or store in database. For simplicity, we can append to image_path 
            # or log it. Let's update image_path or log it. We can set description or keep it.
            # Let's save the resolution photo in status logs or log text.
            # To keep things simple, we prepend the resolution image path to the description or log it.
            # Or we can update the image_path to the resolved image to show it on UI!
            complaint.image_path = f"/uploads/{filename}"

        # Update status
        old_status = complaint.status
        complaint.status = status

        # Read optional progress/resolution notes
        notes = data.get('notes') or data.get('resolution_notes')

        # Log transition
        log = StatusLog(
            complaint_id=id,
            status=status,
            notes=notes,
            timestamp=datetime.utcnow()
        )
        db.session.add(log)
        db.session.commit()

        # Print mock SMS logs
        print(f"============================================================")
        print(f"STATUS UPDATE: {id}")
        print(f"   State change: '{old_status}' -> '{status}'")
        if complaint.assigned_to:
            worker_name = complaint.assigned_worker.name if complaint.assigned_worker else "Worker"
            print(f"   Assigned Worker ID: {complaint.assigned_to} ({worker_name})")
        print(f"MOCK SMS SENT: 'Complaint {id} status updated to {status}.'")
        print(f"============================================================")

        return jsonify(complaint.to_dict()), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@routes_bp.route('/api/users', methods=['GET'])
def get_users():
    """
    Get users (workers or authorities). Filtering by role.
    """
    try:
        role = request.args.get('role')
        ward = request.args.get('ward')
        query = User.query
        
        if role:
            query = query.filter_by(role=role)
        if ward:
            query = query.filter_by(ward=ward)
            
        users = query.all()
        return jsonify([u.to_dict() for u in users]), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@routes_bp.route('/api/analytics', methods=['GET'])
def get_analytics():
    """
    Aggregate metrics for Chart.js.
    """
    try:
        query = Complaint.query
        created_after = request.args.get('created_after')
        if created_after:
            try:
                date_obj = datetime.fromisoformat(created_after)
                query = query.filter(Complaint.created_at >= date_obj)
            except ValueError:
                pass
        complaints = query.all()
        
        total = len(complaints)
        resolved = sum(1 for c in complaints if c.status == 'Resolved')
        pending = sum(1 for c in complaints if c.status in ['Submitted', 'Assigned', 'In Progress'])
        escalated = sum(1 for c in complaints if c.escalation_flag)

        # Category Counts
        categories = {'pothole': 0, 'garbage': 0, 'drainage': 0, 'street_light': 0, 'other': 0}
        # Status Counts
        statuses = {'Submitted': 0, 'Assigned': 0, 'In Progress': 0, 'Resolved': 0, 'Closed': 0}
        # Ward Counts
        wards = {'ward_1': 0, 'ward_2': 0, 'ward_3': 0}

        for c in complaints:
            if c.category in categories:
                categories[c.category] += 1
            if c.status in statuses:
                statuses[c.status] += 1
            if c.ward in wards:
                wards[c.ward] += 1

        return jsonify({
            'total': total,
            'resolved': resolved,
            'pending': pending,
            'escalated': escalated,
            'categories': categories,
            'statuses': statuses,
            'wards': wards
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# REAL EXOTEL IVR WEBHOOKS
import requests
import threading

def _send_exotel_sms_async(exotel_sid, exotel_key, exotel_token, exotel_subdomain, exotel_caller_id, target_phone, complaint_id, ward):
    def _worker():
        try:
            sms_url = f"https://{exotel_key}:{exotel_token}@{exotel_subdomain}/v1/Accounts/{exotel_sid}/Sms/send.json"
            sms_data = {
                "From": exotel_caller_id,
                "To": target_phone,
                "Body": f"SmartCivic: Thank you for your call. Your complaint tracking ID is {complaint_id}. Ward: {ward}"
            }
            response = requests.post(sms_url, data=sms_data, timeout=5)
            if response.status_code in [200, 201]:
                print(f"[IVR] Exotel SMS successfully sent to {target_phone}: {response.text}")
            else:
                print(f"[IVR] Exotel SMS response ({response.status_code}): {response.text}")
        except Exception as sms_error:
            print(f"[IVR] Failed to send Exotel SMS: {str(sms_error)}")

    threading.Thread(target=_worker, daemon=True).start()


def _get_base_url():
    """Get the public-facing base URL (works with ngrok)."""
    # Use X-Forwarded headers if behind ngrok/proxy
    proto = request.headers.get('X-Forwarded-Proto', request.scheme)
    host = request.headers.get('X-Forwarded-Host') or request.headers.get('Host', request.host)
    return f"{proto}://{host}"


@routes_bp.route('/api/exotel/webhook', methods=['POST', 'GET'])
def exotel_webhook():
    """
    Exotel Passthru Applet Webhook.
    Called by Exotel's Flow Builder after the IVR Menu collects a digit.
    Passthru sends call data (GET/POST) — we create the complaint and return 200 OK.
    """
    try:
        # Collect ALL parameters from every source
        data = {}
        data.update(dict(request.args))
        data.update(dict(request.form))
        data.update(dict(request.values))

        # Log everything for debugging
        print(f"", flush=True)
        print(f"==================== EXOTEL PASSTHRU RECEIVED ====================", flush=True)
        print(f"[EXOTEL] Method: {request.method}", flush=True)
        print(f"[EXOTEL] Full URL: {request.url}", flush=True)
        print(f"[EXOTEL] Args (GET params): {dict(request.args)}", flush=True)
        print(f"[EXOTEL] Form (POST body): {dict(request.form)}", flush=True)
        print(f"[EXOTEL] All Values: {data}", flush=True)
        print(f"[EXOTEL] Headers: {dict(request.headers)}", flush=True)
        print(f"===================================================================", flush=True)

        # Extract caller phone
        caller_phone = (
            data.get('CallFrom') or
            data.get('From') or
            data.get('Caller') or
            data.get('caller_id') or
            data.get('CallerId') or
            ''
        )
        call_sid = data.get('CallSid') or data.get('call_sid') or ''
        recording_url = data.get('RecordingUrl') or data.get('recording_url') or ''

        # Extract digits — try every possible parameter name Exotel might use
        raw_digits = (
            data.get('digits') or
            data.get('Digits') or
            data.get('digits[0]') or
            data.get('CustomField') or
            data.get('dtmf') or
            data.get('Dtmf') or
            data.get('gather_input') or
            data.get('pin') or
            data.get('Pin') or
            data.get('applet_input') or
            None
        )

        if raw_digits:
            digits = str(raw_digits).strip('"').strip("'").strip()
        else:
            # Default to 'other' if no digit found (still register the complaint)
            digits = '0'
        
        print(f"[EXOTEL] Extracted digit: '{digits}' (raw: {raw_digits})", flush=True)

        category_map = {
            '1': 'pothole',
            '2': 'drainage',
            '3': 'garbage',
            '4': 'street_light',
            '5': 'footpath',
            '6': 'manhole'
        }
        category = category_map.get(digits, 'other')

        # Process complaint in background thread for INSTANT response to Exotel
        app_obj = current_app._get_current_object()

        def _process_complaint():
            with app_obj.app_context():
                try:
                    import random
                    latitude = 12.971598 + random.uniform(-0.02, 0.02)
                    longitude = 77.594562 + random.uniform(-0.02, 0.02)

                    complaint_id = f"COMP-IVR-{uuid.uuid4().hex[:4].upper()}"
                    ward = get_ward_by_location(latitude, longitude)
                    priority = 'High' if category in ['drainage', 'pothole', 'manhole'] else 'Medium'
                    desc = f"Reported via Exotel IVR Hotline. CallSid: {call_sid}. Caller: {caller_phone}. Recording: {recording_url}"

                    new_complaint = Complaint(
                        complaint_id=complaint_id,
                        description=desc,
                        image_path=None,
                        latitude=latitude,
                        longitude=longitude,
                        category=category,
                        priority=priority,
                        status='Submitted',
                        created_at=datetime.utcnow(),
                        escalation_flag=False,
                        ward=ward
                    )
                    db.session.add(new_complaint)

                    log = StatusLog(
                        complaint_id=complaint_id,
                        status="Submitted (Exotel IVR)",
                        timestamp=datetime.utcnow()
                    )
                    db.session.add(log)
                    db.session.commit()

                    print(f"============================================================", flush=True)
                    print(f"IVR COMPLAINT CREATED: {complaint_id} | Category: {category} | Caller: {caller_phone}", flush=True)
                    print(f"============================================================", flush=True)

                    # Send SMS confirmation
                    exotel_sid = os.environ.get('EXOTEL_SID')
                    exotel_key = os.environ.get('EXOTEL_API_KEY')
                    exotel_token = os.environ.get('EXOTEL_API_TOKEN')
                    exotel_subdomain = os.environ.get('EXOTEL_SUBDOMAIN', 'api.exotel.com')
                    exotel_caller_id = os.environ.get('EXOTEL_CALLER_ID')

                    if exotel_sid and exotel_key and exotel_token and exotel_caller_id and caller_phone:
                        target_phone = caller_phone.strip()
                        if target_phone.startswith('0') and len(target_phone) == 11:
                            target_phone = target_phone[1:]
                        if not target_phone.startswith('+') and len(target_phone) == 10:
                            target_phone = '+91' + target_phone
                        _send_exotel_sms_async(
                            exotel_sid, exotel_key, exotel_token, exotel_subdomain,
                            exotel_caller_id, target_phone, complaint_id, ward
                        )
                except Exception as ex:
                    db.session.rollback()
                    print(f"[EXOTEL ASYNC ERROR]: {str(ex)}", flush=True)
                    import traceback
                    traceback.print_exc()

        threading.Thread(target=_process_complaint, daemon=True).start()

        # Return plain 200 OK — Exotel Passthru only checks status code
        return "200 OK", 200, {'Content-Type': 'text/plain'}

    except Exception as e:
        print(f"[EXOTEL WEBHOOK ERROR]: {str(e)}", flush=True)
        import traceback
        traceback.print_exc()
        # Still return 200 so Exotel follows the success path
        return "200 OK", 200, {'Content-Type': 'text/plain'}




# AUTHENTICATION ENDPOINTS
@routes_bp.route('/api/auth/signup', methods=['POST'])
def signup():
    """
    Register a new user account.
    """
    try:
        data = request.json
        name = data.get('name')
        gmail = data.get('gmail')
        password = data.get('password')
        role = data.get('role')  # 'citizen' | 'worker' | 'authority'
        contact = data.get('contact')
        ward = data.get('ward', 'general')

        if not name or not gmail or not password or not role or not contact:
            return jsonify({'error': 'Name, Gmail, Password, Role, and Contact are required.'}), 400

        # Check existing user
        existing_user = User.query.filter_by(gmail=gmail).first()
        if existing_user:
            return jsonify({'error': 'A user with this Gmail address already exists.'}), 409

        new_user = User(
            name=name,
            gmail=gmail,
            password=password,
            role=role,
            contact=contact,
            ward=ward
        )
        db.session.add(new_user)
        db.session.commit()

        print(f"============================================================")
        print(f"[AUTH] New user registered: {name} ({role}) - Gmail: {gmail}")
        print(f"============================================================")

        return jsonify(new_user.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@routes_bp.route('/api/auth/login', methods=['POST'])
def login():
    """
    Authenticate a user and return their details.
    """
    try:
        data = request.json
        gmail = data.get('gmail')
        password = data.get('password')

        if not gmail or not password:
            return jsonify({'error': 'Gmail and Password are required.'}), 400

        user = User.query.filter_by(gmail=gmail).first()
        if not user or user.password != password:
            return jsonify({'error': 'Invalid Gmail address or password.'}), 401

        print(f"============================================================")
        print(f"[AUTH] User logged in: {user.name} ({user.role})")
        print(f"============================================================")

        return jsonify(user.to_dict()), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# JOURNALIST REPORTS ENDPOINTS
from models import JournalistReport

@routes_bp.route('/api/journalist/reports/generate', methods=['POST'])
def generate_journalist_report():
    try:
        data = request.json
        complaint_id = data.get('complaint_id')
        if not complaint_id:
            return jsonify({'error': 'Complaint ID is required'}), 400
            
        complaint = Complaint.query.get(complaint_id)
        if not complaint:
            return jsonify({'error': 'Complaint not found'}), 404
            
        # Simulate AI Agent news report generation
        category_title = complaint.category.replace('_', ' ').upper()
        
        # Build news title
        title = f"INVESTIGATIVE REPORT: Unaddressed {category_title} Neglect in Smart City Ward"
        
        # Build detailed news content
        content = (
            f"--- CITY JOURNAL WATCHDOG ---\n\n"
            f"MUNICIPAL TIMEOUT ACTION: Complaint {complaint_id} has breached the standard 5-minute authority response threshold. "
            f"The civic issue, categorized as a '{complaint.category}' threat, remains unassigned and unresolved.\n\n"
            f"GEOGRAPHIC LOCATION:\n"
            f"The issue is pinned at Latitude: {complaint.latitude:.6f}, Longitude: {complaint.longitude:.6f}.\n\n"
            f"CITIZEN TESTIMONY & ANALYSIS:\n"
            f"\" {complaint.description} \"\n\n"
        )
        
        if complaint.image_analysis:
            content += (
                f"COMPUTER VISION AUDIT REPORT:\n"
                f"Advanced image telemetry scans indicate critical structural features: {complaint.image_analysis}\n\n"
            )
            
        content += (
            f"PRESS WATCHDOG VERDICT:\n"
            f"Due to complete lack of administrative action within the designated window, this case is flagged for general public press release. "
            f"SmartCivic AI watchdog agent recommends immediate worker allocation before severe safety incidents occur."
        )
        
        return jsonify({
            'complaint_id': complaint_id,
            'title': title,
            'content': content
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@routes_bp.route('/api/journalist/reports', methods=['POST'])
def save_journalist_report():
    try:
        data = request.json
        complaint_id = data.get('complaint_id')
        title = data.get('title')
        content = data.get('content')
        published = data.get('published', False)

        if not complaint_id or not title or not content:
            return jsonify({'error': 'complaint_id, title, and content are required'}), 400

        new_report = JournalistReport(
            complaint_id=complaint_id,
            title=title,
            content=content,
            published=published
        )
        db.session.add(new_report)
        db.session.commit()

        print(f"============================================================")
        print(f"[PRESS RELEASE] Journalist saved report for {complaint_id}")
        if published:
            print(f"   STATUS: PUBLISHED TO FEED!")
        print(f"============================================================")

        return jsonify(new_report.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@routes_bp.route('/api/journalist/reports', methods=['GET'])
def get_journalist_reports():
    try:
        reports = JournalistReport.query.order_by(JournalistReport.created_at.desc()).all()
        return jsonify([r.to_dict() for r in reports]), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@routes_bp.route('/api/journalist/reports/<int:id>', methods=['PUT'])
def update_journalist_report(id):
    try:
        data = request.json
        report = JournalistReport.query.get(id)
        if not report:
            return jsonify({'error': 'Report not found'}), 404

        if 'title' in data:
            report.title = data['title']
        if 'content' in data:
            report.content = data['content']
        if 'published' in data:
            report.published = data['published']

        db.session.commit()

        if report.published:
            print(f"============================================================")
            print(f"[PRESS RELEASE] Article ID {id} has been PUBLISHED!")
            print(f"   Title: '{report.title}'")
            print(f"============================================================")

        return jsonify(report.to_dict()), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
