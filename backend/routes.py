import os
import io
import csv
import uuid
import secrets
import traceback
from datetime import datetime, timezone, timedelta
from functools import wraps
from flask import Blueprint, request, jsonify, Response, current_app, render_template, session, redirect, url_for, make_response
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

from models import (
    db, User, Complaint, StatusLog, JournalistReport,
    ComplaintEvidence, Notification, Comment, Feedback, Escalation, AuditLog,
    log_audit, create_notification, utc_now
)
from ai_processor import (
    classify_complaint_text, haversine_distance, get_image_similarity,
    analyze_and_describe_image, extract_exif_gps, parse_coordinates_from_text,
    extract_text_from_image_watermark
)
from hf_multilingual import (
    classify_complaint_multilingual,
    translate_text,
    detect_language,
    SUPPORTED_LANGUAGES
)
from email_service import (
    send_complaint_confirmation_email,
    send_complaint_status_update_email,
    send_welcome_email,
    send_geotag_authority_alert,
    send_geotag_worker_assignment,
    send_authority_pending_approval_email,
    send_authority_approval_email,
    send_authority_key_regenerated_email,
    send_authority_rejection_email
)

routes_bp = Blueprint('routes', __name__)

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'gif', 'mp4', 'mov', 'avi', 'mkv', 'webm'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# -------------------------------------------------------------
# Authentication & Authorization Helpers
# -------------------------------------------------------------
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_admin'):
            if request.path.startswith('/api/admin'):
                return jsonify({'error': 'Unauthorized: Master Admin login required.'}), 401
            return redirect('/admin/login')
        return f(*args, **kwargs)
    return decorated_function

def generate_secret_key():
    return f"AUTH-{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}"

def get_current_user_from_request():
    """
    Extracts authenticated user from headers or session if provided.
    Supports X-User-Id, X-User-Role, Authorization, or Flask session.
    """
    user_id = request.headers.get('X-User-Id')
    if user_id:
        try:
            return User.query.get(int(user_id))
        except (ValueError, TypeError):
            pass
    if session.get('user_id'):
        return User.query.get(session['user_id'])
    return None

def verify_password(stored_password, provided_password):
    if not stored_password or not provided_password:
        return False
    if stored_password.startswith(('scrypt:', 'pbkdf2:', 'bcrypt:', 'argon2:')):
        try:
            if check_password_hash(stored_password, provided_password):
                return True
        except Exception:
            pass
    return stored_password == provided_password

# Strict Lifecycle State Machine Transitions
VALID_TRANSITIONS = {
    'Submitted': ['Verified', 'Assigned', 'Rejected', 'In Progress', 'Escalated'],
    'Verified': ['Assigned', 'In Progress', 'Rejected', 'Escalated'],
    'Assigned': ['In Progress', 'Assigned', 'Completed', 'Resolved', 'Escalated', 'Verified'],
    'In Progress': ['Completed', 'Resolved', 'Assigned', 'Escalated'],
    'Completed': ['Closed', 'Reopened', 'Resolved', 'In Progress'],
    'Resolved': ['Closed', 'Reopened', 'Completed', 'In Progress'],
    'Closed': ['Reopened'],
    'Reopened': ['In Progress', 'Assigned', 'Completed', 'Verified'],
    'Rejected': []  # Terminal
}

# Helper function for smart ward routing
def get_ward_by_location(lat, lng):
    if lat > 12.97:
        return 'ward_1' if lng < 77.59 else 'ward_2'
    else:
        return 'ward_3'

def normalize_category(cat_str):
    if not cat_str:
        return 'other'
    c = cat_str.strip().lower().replace(' ', '_').replace('-', '_')
    mapping = {
        'pothole': 'pothole',
        'potholes': 'pothole',
        'garbage': 'garbage',
        'waste': 'garbage',
        'drainage': 'drainage',
        'open_drain': 'open_drain',
        'sewage': 'sewage_overflow',
        'sewage_overflow': 'sewage_overflow',
        'water_leakage': 'water_leakage',
        'leakage': 'water_leakage',
        'street_light': 'street_light',
        'broken_streetlights': 'street_light',
        'streetlight': 'street_light',
        'road_damage': 'road_damage',
        'fallen_tree': 'fallen_tree',
        'illegal_dumping': 'illegal_dumping',
        'public_toilet': 'public_toilet',
        'public_toilet_issues': 'public_toilet',
        'footpath': 'road_damage',
        'manhole': 'open_drain'
    }
    return mapping.get(c, c)

# -------------------------------------------------------------
# GEOTAG & PREVIEW ENDPOINT
# -------------------------------------------------------------
@routes_bp.route('/api/parse-geotag', methods=['POST'])
def parse_geotag_endpoint():
    """
    Instantly extracts GPS latitude & longitude from an uploaded photo.
    """
    try:
        image_file = request.files.get('image')
        if not image_file or not image_file.filename:
            return jsonify({'found': False, 'message': 'No image file provided.'}), 400

        temp_filename = f"PREVIEW_{uuid.uuid4().hex[:6]}_{secure_filename(image_file.filename)}"
        temp_path = os.path.join(UPLOAD_FOLDER, temp_filename)
        image_file.save(temp_path)

        lat, lng = None, None

        # 1. Try EXIF GPS metadata extraction
        try:
            ex_lat, ex_lng = extract_exif_gps(temp_path)
            if ex_lat is not None and ex_lng is not None:
                lat, lng = ex_lat, ex_lng
        except Exception as ex_err:
            print(f"[PREVIEW GEOTAG EXIF WARNING] {ex_err}")

        # 2. Try text / regex scanning from description or filename
        if lat is None or lng is None:
            desc = request.form.get('description', '') or image_file.filename
            txt_lat, txt_lng = parse_coordinates_from_text(desc)
            if txt_lat is not None and txt_lng is not None:
                lat, lng = txt_lat, txt_lng

        # 3. Try OCR on image watermark
        if lat is None or lng is None:
            try:
                ocr_lat, ocr_lng = extract_text_from_image_watermark(temp_path)
                if ocr_lat is not None and ocr_lng is not None:
                    lat, lng = ocr_lat, ocr_lng
            except Exception as ocr_err:
                print(f"[PREVIEW GEOTAG OCR WARNING] {ocr_err}")

        # Clean up temp file
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass

        if lat is not None and lng is not None:
            ward = get_ward_by_location(lat, lng)
            return jsonify({
                'found': True,
                'latitude': lat,
                'longitude': lng,
                'ward': ward
            }), 200

        return jsonify({'found': False, 'message': 'No GPS geotag found in photo.'}), 200
    except Exception as e:
        return jsonify({'found': False, 'error': str(e)}), 500

# -------------------------------------------------------------
# COMPLAINTS ENDPOINTS
# -------------------------------------------------------------
@routes_bp.route('/api/complaints', methods=['POST'])
def create_complaint():
    """
    Creates a new complaint. Runs AI duplicate check and text classification.
    Supports title, category, priority, GPS, photos, videos, and SLA deadline calculation.
    """
    try:
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        latitude_str = request.form.get('latitude')
        longitude_str = request.form.get('longitude')
        contact = request.form.get('contact', '').strip()
        citizen_gmail = request.form.get('gmail') or request.form.get('citizen_gmail') or ''
        raw_category = request.form.get('category', '').strip()
        raw_priority = request.form.get('priority', '').strip()

        if not description or not latitude_str or not longitude_str:
            return jsonify({'error': 'Description, latitude, and longitude are required.'}), 400

        try:
            latitude = float(latitude_str)
            longitude = float(longitude_str)
        except ValueError:
            return jsonify({'error': 'Invalid latitude or longitude values.'}), 400

        complaint_id = f"COMP-{uuid.uuid4().hex[:6].upper()}"

        # Handle image / video upload & Geotag extraction
        image_file = request.files.get('image')
        image_path = None
        is_video = False
        if image_file and image_file.filename:
            filename = f"{complaint_id}_{secure_filename(image_file.filename)}"
            save_path = os.path.join(UPLOAD_FOLDER, filename)
            image_file.save(save_path)
            image_path = f"/uploads/{filename}"

            ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
            is_video = ext in ['mp4', 'mov', 'avi', 'mkv', 'webm']

            if not is_video:
                # Auto-extract EXIF GPS location
                ex_lat, ex_lng = extract_exif_gps(save_path)
                if ex_lat is not None and ex_lng is not None:
                    latitude = ex_lat
                    longitude = ex_lng
                else:
                    try:
                        ocr_lat, ocr_lng = extract_text_from_image_watermark(save_path)
                        if ocr_lat is not None and ocr_lng is not None:
                            latitude = ocr_lat
                            longitude = ocr_lng
                    except Exception as ocr_err:
                        print(f"[AI GEOTAG EXTRACTOR OCR WARNING] {ocr_err}")

        # Parse text/description for geotag coordinates
        txt_lat, txt_lng = parse_coordinates_from_text(description)
        if txt_lat is not None and txt_lng is not None:
            latitude = txt_lat
            longitude = txt_lng

        # Smart Ward Routing
        ward = get_ward_by_location(latitude, longitude)

        # AI Multilingual Classifier with Hugging Face: Auto category & priority across Kannada, Hindi, Telugu, English
        multi_ai = classify_complaint_multilingual(description, title=title)
        detected_lang = multi_ai.get('language', 'en')
        classified_cat = multi_ai.get('category', 'other')
        classified_prio = multi_ai.get('priority', 'Medium')

        category = normalize_category(raw_category) if raw_category else classified_cat
        priority = raw_priority if raw_priority in ['High', 'Medium', 'Low'] else classified_prio

        if not title:
            if detected_lang != 'en' and multi_ai.get('title_en'):
                title = f"{multi_ai.get('title_en')} in {ward.replace('_', ' ').title()}"
            else:
                title = f"{category.replace('_', ' ').title()} in {ward.replace('_', ' ').title()}"

        # Compute SLA Deadline based on priority
        deadline_hours = 24 if priority == 'High' else (48 if priority == 'Medium' else 72)
        deadline = datetime.now(timezone.utc) + timedelta(hours=deadline_hours)

        # Auto-Assign to Ward Worker if available
        assigned_worker = User.query.filter_by(role='worker', ward=ward).first()
        if not assigned_worker:
            assigned_worker = User.query.filter_by(role='worker').first()

        assigned_to_id = assigned_worker.id if assigned_worker else None
        initial_status = 'Assigned' if assigned_worker else 'Submitted'

        # AI Duplicate Check: Find nearby complaints (50m radius)
        duplicate_flag = False
        duplicate_of = None
        existing_complaints = Complaint.query.filter(
            Complaint.status.in_(['Submitted', 'Verified', 'Assigned', 'In Progress'])
        ).all()

        for ext in existing_complaints:
            dist = haversine_distance(latitude, longitude, ext.latitude, ext.longitude)
            if dist <= 50.0:
                if image_path and ext.image_path and not is_video:
                    abs_path_new = os.path.join(os.path.dirname(__file__), image_path.lstrip('/'))
                    abs_path_ext = os.path.join(os.path.dirname(__file__), ext.image_path.lstrip('/'))
                    similarity = get_image_similarity(abs_path_new, abs_path_ext)
                    if similarity > 0.82:
                        duplicate_flag = True
                        duplicate_of = ext.complaint_id
                        break
                else:
                    if category == ext.category:
                        duplicate_flag = True
                        duplicate_of = ext.complaint_id
                        break

        # Run image analysis
        image_analysis = None
        if image_path and not is_video:
            try:
                abs_path_new = os.path.join(os.path.dirname(__file__), image_path.lstrip('/'))
                image_analysis = analyze_and_describe_image(abs_path_new)
            except Exception as img_err:
                print(f"[WARNING] Image analysis skipped: {img_err}")

        # Save Complaint
        now = datetime.now(timezone.utc)
        new_complaint = Complaint(
            complaint_id=complaint_id,
            title=title,
            description=description,
            image_path=image_path,
            latitude=latitude,
            longitude=longitude,
            category=category,
            priority=priority,
            status=initial_status,
            assigned_to=assigned_to_id,
            created_at=now,
            opened_at=now if assigned_worker else None,
            deadline=deadline,
            duplicate_of_id=duplicate_of,
            escalation_flag=duplicate_flag,
            ward=ward,
            image_analysis=image_analysis,
            citizen_gmail=citizen_gmail if citizen_gmail else None
        )
        db.session.add(new_complaint)
        db.session.flush()

        # Save Initial Evidence
        if image_path:
            evidence = ComplaintEvidence(
                complaint_id=complaint_id,
                evidence_type='citizen',
                file_path=image_path,
                file_type='video' if is_video else 'image',
                uploader_name='Citizen Reporter',
                uploader_role='citizen',
                notes='Initial issue submission proof'
            )
            db.session.add(evidence)

        # Initial Status Log
        log_status_name = f"Assigned to {assigned_worker.name} ({ward})" if assigned_worker else "Submitted"
        log = StatusLog(
            complaint_id=complaint_id,
            status=initial_status,
            previous_status=None,
            notes=f"Complaint registered. {log_status_name}",
            user_name='System Dispatch',
            user_role='system',
            timestamp=now
        )
        db.session.add(log)

        # Record in Audit Log
        log_audit(
            action="COMPLAINT_CREATED",
            complaint_id=complaint_id,
            details=f"Category: {category}, Priority: {priority}, Ward: {ward}, Assigned: {assigned_worker.name if assigned_worker else 'None'}"
        )

        # In-App Notification for Corporators in that ward
        create_notification(
            title=f"New Issue: {title}",
            message=f"New {category} complaint registered in {ward.replace('_', ' ').title()}. Priority: {priority}.",
            ward=ward,
            user_role='authority',
            complaint_id=complaint_id,
            category='submission'
        )

        db.session.commit()

        # Format return data
        response_data = new_complaint.to_dict()
        response_data['is_duplicate'] = duplicate_flag
        response_data['duplicate_of'] = duplicate_of
        response_data['detected_language'] = detected_lang
        response_data['english_title'] = multi_ai.get('title_en')
        response_data['english_description'] = multi_ai.get('description_en')

        # Send confirmation email to Citizen if provided
        if citizen_gmail:
            try:
                user_account = User.query.filter_by(gmail=citizen_gmail).first()
                sender_g = user_account.gmail if user_account else citizen_gmail
                sender_p = user_account.password if user_account else None
                send_complaint_confirmation_email(citizen_gmail, response_data, sender_gmail=sender_g, sender_password=sender_p)
            except Exception as mail_err:
                print(f"[WARNING] Citizen confirmation email error: {mail_err}")

        # Send Geotag Alert Email to Authorities in that Ward
        authorities = User.query.filter_by(role='authority', ward=ward).all()
        if not authorities:
            authorities = User.query.filter_by(role='authority').all()

        for auth in authorities:
            if auth.gmail:
                try:
                    send_geotag_authority_alert(auth.gmail, response_data)
                except Exception as auth_err:
                    print(f"[WARNING] Geotag authority dispatch email error: {auth_err}")

        # Send Geotag Task Assignment Email to Assigned Worker
        if assigned_worker and assigned_worker.gmail:
            try:
                send_geotag_worker_assignment(assigned_worker.gmail, response_data)
            except Exception as wrk_err:
                print(f"[WARNING] Geotag worker dispatch email error: {wrk_err}")

        return jsonify(response_data), 201

    except Exception as e:
        db.session.rollback()
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@routes_bp.route('/api/complaints', methods=['GET'])
def get_complaints():
    """
    Get list of complaints. Supports filtering by ward, status, priority, category,
    citizen_gmail, assigned_to, search, and enforces role-based ward boundaries for corporators.
    """
    try:
        query = Complaint.query
        current_user = get_current_user_from_request()

        # Filters
        ward = request.args.get('ward')
        status = request.args.get('status')
        priority = request.args.get('priority')
        category = request.args.get('category')
        citizen_gmail = request.args.get('citizen_gmail')
        assigned_to = request.args.get('assigned_to')
        escalated = request.args.get('escalated')
        overdue = request.args.get('overdue')
        search = request.args.get('search')
        redirected_to_journalist = request.args.get('redirected_to_journalist')
        created_after = request.args.get('created_after')

        # Role-based ward isolation:
        # A corporator (role='authority') should only see their assigned ward, unless higher authority or admin
        if current_user and current_user.role == 'authority' and current_user.ward and current_user.ward != 'all':
            query = query.filter_by(ward=current_user.ward)
        elif ward:
            query = query.filter_by(ward=ward)

        if status:
            query = query.filter_by(status=status)
        if priority:
            query = query.filter_by(priority=priority)
        if category:
            query = query.filter_by(category=category)
        if citizen_gmail:
            query = query.filter_by(citizen_gmail=citizen_gmail)
        if assigned_to:
            try:
                query = query.filter_by(assigned_to=int(assigned_to))
            except ValueError:
                pass
        if escalated is not None:
            val = escalated.lower() in ['true', '1']
            query = query.filter_by(escalation_flag=val)
        if overdue is not None:
            val = overdue.lower() in ['true', '1']
            query = query.filter_by(overdue_flag=val)
        if redirected_to_journalist is not None:
            val = redirected_to_journalist.lower() in ['true', '1']
            query = query.filter_by(redirected_to_journalist=val)
        if search:
            s = f"%{search.strip()}%"
            query = query.filter(
                (Complaint.complaint_id.ilike(s)) |
                (Complaint.title.ilike(s)) |
                (Complaint.description.ilike(s)) |
                (Complaint.category.ilike(s))
            )
        if created_after:
            try:
                date_obj = datetime.fromisoformat(created_after)
                query = query.filter(Complaint.created_at >= date_obj)
            except ValueError:
                pass

        complaints = query.order_by(Complaint.created_at.desc()).all()
        return jsonify([c.to_dict() for c in complaints]), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@routes_bp.route('/api/heatmap/summary', methods=['GET'])
def get_heatmap_summary():
    """
    Get aggregated regional complaint density and coordinates for heatmaps.
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
                    'lats': [],
                    'lngs': []
                }
            ward_map[w]['count'] += 1
            ward_map[w]['lats'].append(c.latitude)
            ward_map[w]['lngs'].append(c.longitude)

        summary = []
        points = []
        for w, data in ward_map.items():
            avg_lat = sum(data['lats']) / len(data['lats']) if data['lats'] else 12.97
            avg_lng = sum(data['lngs']) / len(data['lngs']) if data['lngs'] else 77.59
            cnt = data['count']
            level = 'High' if cnt > 5 else ('Moderate' if cnt >= 3 else 'Low')
            color = '#ef4444' if cnt > 5 else ('#f59e0b' if cnt >= 3 else '#10b981')

            summary.append({
                'ward': w,
                'count': cnt,
                'level': level,
                'color': color,
                'center': [avg_lat, avg_lng]
            })

            # Add individual heat points
            for lat, lng in zip(data['lats'], data['lngs']):
                points.append([lat, lng, 0.7 if cnt > 5 else 0.4])

        return jsonify({
            'regional_summary': summary,
            'heat_points': points
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@routes_bp.route('/api/complaints/<id>', methods=['GET'])
def get_complaint_by_id(id):
    """
    Get a single complaint, its timeline history, multi-stage evidences, comments, and feedbacks.
    """
    try:
        complaint = Complaint.query.get(id)
        if not complaint:
            return jsonify({'error': 'Complaint not found'}), 404

        logs = StatusLog.query.filter_by(complaint_id=id).order_by(StatusLog.timestamp.asc()).all()
        evidences = ComplaintEvidence.query.filter_by(complaint_id=id).order_by(ComplaintEvidence.created_at.asc()).all()
        comments = Comment.query.filter_by(complaint_id=id).order_by(Comment.created_at.asc()).all()
        feedbacks = Feedback.query.filter_by(complaint_id=id).all()
        escalations = Escalation.query.filter_by(complaint_id=id).order_by(Escalation.created_at.asc()).all()

        data = complaint.to_dict()
        data['history'] = [l.to_dict() for l in logs]
        data['evidences'] = [e.to_dict() for e in evidences]
        data['comments'] = [c.to_dict() for c in comments]
        data['feedbacks'] = [f.to_dict() for f in feedbacks]
        data['escalations'] = [esc.to_dict() for esc in escalations]
        return jsonify(data), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@routes_bp.route('/api/complaints/<id>', methods=['PUT'])
def update_complaint(id):
    """
    Updates status, worker assignment, priority, notes, and evidence.
    Validates lifecycle transitions and user permissions.
    """
    try:
        complaint = Complaint.query.get(id)
        if not complaint:
            return jsonify({'error': 'Complaint not found'}), 404

        current_user = get_current_user_from_request()

        # Read JSON or Form data
        if request.is_json:
            data = request.json or {}
        else:
            data = request.form or {}

        status = data.get('status')
        assigned_to = data.get('assigned_to')
        priority = data.get('priority')
        deadline_str = data.get('deadline')
        notes = data.get('notes') or data.get('resolution_notes')
        user_name = data.get('user_name') or (current_user.name if current_user else 'System')
        user_role = data.get('user_role') or (current_user.role if current_user else 'authority')

        # Check Lifecycle Transition validity if status is changing
        old_status = complaint.status
        if status and status != old_status:
            allowed_next = VALID_TRANSITIONS.get(old_status, [])
            if allowed_next and status not in allowed_next:
                return jsonify({
                    'error': f"Invalid status transition from '{old_status}' to '{status}'. Allowed: {', '.join(allowed_next)}"
                }), 400

        # Enforce worker permission check:
        # A worker should only modify tasks assigned to them
        if current_user and current_user.role == 'worker':
            if complaint.assigned_to and complaint.assigned_to != current_user.id:
                return jsonify({'error': 'Unauthorized: You can only update complaints assigned to you.'}), 403

        # Enforce corporator ward permission check
        if current_user and current_user.role == 'authority' and current_user.ward and current_user.ward != 'all':
            if complaint.ward != current_user.ward:
                return jsonify({'error': f"Unauthorized: Corporator belongs to {current_user.ward}, but complaint is in {complaint.ward}."}), 403

        # Update assignment
        if assigned_to is not None:
            if str(assigned_to).strip() == "" or assigned_to == 0:
                complaint.assigned_to = None
            else:
                try:
                    worker_id = int(assigned_to)
                    worker = User.query.get(worker_id)
                    if worker:
                        complaint.assigned_to = worker_id
                        if not status or status == 'Submitted' or status == 'Verified':
                            status = 'Assigned'
                except ValueError:
                    pass

        # Update priority & deadline
        if priority:
            complaint.priority = priority
        if deadline_str:
            try:
                complaint.deadline = datetime.fromisoformat(deadline_str)
            except ValueError:
                pass

        # Manage status milestone timestamps
        now = datetime.now(timezone.utc)
        if status == 'Verified' and not complaint.verified_at:
            complaint.verified_at = now
        if status in ['Assigned', 'In Progress'] and not complaint.opened_at:
            complaint.opened_at = now
        if status in ['Completed', 'Resolved'] and not complaint.completed_at:
            complaint.completed_at = now
        if status == 'Closed' and not complaint.closed_at:
            complaint.closed_at = now

        # Handle resolution image file upload
        resolution_file = request.files.get('resolution_image') if not request.is_json else None
        if resolution_file and resolution_file.filename:
            filename = f"RESOLVED_{id}_{secure_filename(resolution_file.filename)}"
            save_path = os.path.join(UPLOAD_FOLDER, filename)
            resolution_file.save(save_path)
            resolved_url = f"/uploads/{filename}"
            complaint.resolved_image_path = resolved_url
            complaint.image_path = resolved_url

            # Save as after-work evidence
            evidence = ComplaintEvidence(
                complaint_id=id,
                evidence_type='after',
                file_path=resolved_url,
                file_type='image',
                uploader_name=user_name,
                uploader_role=user_role,
                notes=notes or 'Completion / Resolution Proof'
            )
            db.session.add(evidence)

        # Update status
        if status:
            complaint.status = status

        # Log transition in StatusLog
        log = StatusLog(
            complaint_id=id,
            status=status or old_status,
            previous_status=old_status,
            notes=notes,
            user_id=current_user.id if current_user else None,
            user_name=user_name,
            user_role=user_role,
            timestamp=now
        )
        db.session.add(log)

        # Audit Log
        log_audit(
            action=f"STATUS_UPDATED_{status.upper() if status else 'MODIFIED'}",
            complaint_id=id,
            user=current_user,
            details=f"Status: '{old_status}' -> '{status or old_status}'. Notes: {notes or 'N/A'}"
        )

        # Persistent In-App Notification
        if status and status != old_status:
            create_notification(
                title=f"Complaint {id} Updated",
                message=f"Status changed to {status}. Notes: {notes or 'No remarks'}",
                recipient_email=complaint.citizen_gmail,
                complaint_id=id,
                category='status'
            )

        db.session.commit()

        # Send status update email to citizen if available
        if complaint.citizen_gmail:
            try:
                user_account = User.query.filter_by(gmail=complaint.citizen_gmail).first()
                sender_g = user_account.gmail if user_account else complaint.citizen_gmail
                sender_p = user_account.password if user_account else None
                send_complaint_status_update_email(complaint.citizen_gmail, complaint.to_dict(), notes, sender_gmail=sender_g, sender_password=sender_p)
            except Exception as mail_err:
                print(f"[WARNING] Status update email error: {mail_err}")

        return jsonify(complaint.to_dict()), 200

    except Exception as e:
        db.session.rollback()
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@routes_bp.route('/api/complaints/<id>/verify', methods=['POST'])
def verify_initial_complaint(id):
    """
    Corporator or Authority accepts/verifies a complaint report.
    Transitions status from Submitted to Verified.
    """
    try:
        complaint = Complaint.query.get(id)
        if not complaint:
            return jsonify({'error': 'Complaint not found'}), 404

        current_user = get_current_user_from_request()
        if current_user and current_user.role == 'authority' and current_user.ward and current_user.ward != 'all':
            if complaint.ward != current_user.ward:
                return jsonify({'error': f"Unauthorized: Corporator belongs to {current_user.ward}, but complaint is in {complaint.ward}."}), 403

        old_status = complaint.status
        complaint.status = 'Verified'
        
        user_name = current_user.name if current_user else 'Corporator'
        log = StatusLog(
            complaint_id=complaint.complaint_id,
            status='Verified',
            user_name=user_name,
            user_role='authority',
            notes='Complaint report verified by Ward Authority'
        )
        db.session.add(log)
        
        log_audit(
            action='VERIFY',
            user=current_user,
            complaint_id=complaint.complaint_id,
            details=f"Status transitioned from {old_status} to Verified"
        )
        
        if complaint.citizen_gmail:
            try:
                send_complaint_status_update_email(
                    complaint.citizen_gmail,
                    complaint.to_dict(),
                    notes='Your complaint has been verified by the municipal authority.'
                )
            except Exception as mail_err:
                print(f"[EMAIL WARNING] Verification email failed: {mail_err}")
            
        db.session.commit()
        return jsonify(complaint.to_dict()), 200
    except Exception as e:
        db.session.rollback()
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@routes_bp.route('/api/complaints/<id>/reject', methods=['POST'])
def reject_complaint(id):
    """
    Corporator or Authority rejects a complaint. Requires a mandatory rejection reason.
    """
    try:
        complaint = Complaint.query.get(id)
        if not complaint:
            return jsonify({'error': 'Complaint not found'}), 404

        data = request.json or {}
        reason = data.get('rejection_reason', '').strip()
        if not reason:
            return jsonify({'error': 'Mandatory rejection reason must be provided.'}), 400

        current_user = get_current_user_from_request()
        user_name = data.get('user_name') or (current_user.name if current_user else 'Authority')
        user_role = data.get('user_role') or (current_user.role if current_user else 'authority')

        old_status = complaint.status
        complaint.status = 'Rejected'
        complaint.rejection_reason = reason

        now = datetime.now(timezone.utc)
        log = StatusLog(
            complaint_id=id,
            status='Rejected',
            previous_status=old_status,
            notes=f"Complaint Rejected. Reason: {reason}",
            user_id=current_user.id if current_user else None,
            user_name=user_name,
            user_role=user_role,
            timestamp=now
        )
        db.session.add(log)

        log_audit(
            action="COMPLAINT_REJECTED",
            complaint_id=id,
            user=current_user,
            details=f"Rejected. Reason: {reason}"
        )

        create_notification(
            title=f"Complaint {id} Rejected",
            message=f"Your complaint was rejected by municipal authority. Reason: {reason}",
            recipient_email=complaint.citizen_gmail,
            complaint_id=id,
            category='status'
        )

        db.session.commit()
        return jsonify(complaint.to_dict()), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@routes_bp.route('/api/complaints/<id>/verify-resolution', methods=['POST'])
def verify_resolution(id):
    """
    Citizen Verification Flow:
    Citizen views completed work and can:
    1. Accept Resolution -> Status becomes 'Closed', records rating (1-5), satisfaction, feedback.
    2. Reject Resolution -> Status becomes 'Reopened', increments reopen_count, returns to In Progress.
    """
    try:
        complaint = Complaint.query.get(id)
        if not complaint:
            return jsonify({'error': 'Complaint not found'}), 404

        data = request.json or {}
        action = data.get('action', '').strip().lower()  # 'accept' or 'reject'
        rating = data.get('rating')
        satisfaction = data.get('satisfaction', 'satisfactory')
        feedback_text = data.get('feedback', '').strip()
        reason = data.get('reason', '').strip() or feedback_text

        current_user = get_current_user_from_request()
        user_name = data.get('user_name') or (current_user.name if current_user else 'Citizen')
        now = datetime.now(timezone.utc)
        old_status = complaint.status

        if action == 'accept':
            complaint.status = 'Closed'
            complaint.closed_at = now
            complaint.citizen_rating = int(rating) if rating else 5
            complaint.citizen_feedback = feedback_text
            complaint.citizen_satisfied = True

            # Save Feedback Record
            fb = Feedback(
                complaint_id=id,
                citizen_gmail=complaint.citizen_gmail,
                rating=complaint.citizen_rating,
                satisfaction='satisfactory',
                comment=feedback_text
            )
            db.session.add(fb)

            log = StatusLog(
                complaint_id=id,
                status='Closed',
                previous_status=old_status,
                notes=f"Citizen verified and accepted resolution. Rating: {complaint.citizen_rating}/5. Feedback: {feedback_text}",
                user_name=user_name,
                user_role='citizen',
                timestamp=now
            )
            db.session.add(log)

            log_audit(
                action="CITIZEN_ACCEPTED_RESOLUTION",
                complaint_id=id,
                user=current_user,
                details=f"Closed with {complaint.citizen_rating}-star rating: {feedback_text}"
            )

            create_notification(
                title=f"Complaint {id} Closed by Citizen",
                message=f"Citizen accepted resolution with {complaint.citizen_rating} stars.",
                ward=complaint.ward,
                user_role='authority',
                complaint_id=id,
                category='completion'
            )

        elif action == 'reject':
            if not reason:
                return jsonify({'error': 'Mandatory reason required for rejecting resolution and reopening.'}), 400

            complaint.status = 'Reopened'
            complaint.reopen_count = (complaint.reopen_count or 0) + 1
            complaint.reopened_reason = reason
            complaint.citizen_satisfied = False

            fb = Feedback(
                complaint_id=id,
                citizen_gmail=complaint.citizen_gmail,
                rating=int(rating) if rating else 1,
                satisfaction='unsatisfactory',
                comment=reason
            )
            db.session.add(fb)

            log = StatusLog(
                complaint_id=id,
                status='Reopened',
                previous_status=old_status,
                notes=f"Citizen marked resolution unsatisfactory and reopened complaint. Reason: {reason}",
                user_name=user_name,
                user_role='citizen',
                timestamp=now
            )
            db.session.add(log)

            log_audit(
                action="CITIZEN_REOPENED_COMPLAINT",
                complaint_id=id,
                user=current_user,
                details=f"Reopened (Count {complaint.reopen_count}). Reason: {reason}"
            )

            create_notification(
                title=f"Complaint {id} REOPENED by Citizen!",
                message=f"Citizen rejected resolution in {complaint.ward}. Reason: {reason}",
                ward=complaint.ward,
                user_role='authority',
                complaint_id=id,
                category='reopen'
            )
        else:
            return jsonify({'error': "Invalid action. Use 'accept' or 'reject'."}), 400

        db.session.commit()
        return jsonify(complaint.to_dict()), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@routes_bp.route('/api/complaints/<id>/evidence', methods=['POST'])
def upload_evidence(id):
    """
    Multi-stage evidence upload:
    - evidence_type: 'before' | 'progress' | 'after' | 'inspection'
    """
    try:
        complaint = Complaint.query.get(id)
        if not complaint:
            return jsonify({'error': 'Complaint not found'}), 404

        evidence_file = request.files.get('image') or request.files.get('file')
        if not evidence_file or not evidence_file.filename:
            return jsonify({'error': 'Evidence file is required.'}), 400

        evidence_type = request.form.get('evidence_type', 'progress').lower()
        notes = request.form.get('notes', '').strip()
        current_user = get_current_user_from_request()
        uploader_name = request.form.get('uploader_name') or (current_user.name if current_user else 'Field Personnel')
        uploader_role = request.form.get('uploader_role') or (current_user.role if current_user else 'worker')

        filename = f"{evidence_type.upper()}_{id}_{secure_filename(evidence_file.filename)}"
        save_path = os.path.join(UPLOAD_FOLDER, filename)
        evidence_file.save(save_path)
        file_url = f"/uploads/{filename}"

        ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
        file_type = 'video' if ext in ['mp4', 'mov', 'avi', 'mkv', 'webm'] else 'image'

        # Link to complaint model fields
        if evidence_type == 'before':
            complaint.before_image_path = file_url
        elif evidence_type == 'progress':
            complaint.progress_image_path = file_url
        elif evidence_type in ['after', 'resolution']:
            complaint.resolved_image_path = file_url
            complaint.image_path = file_url
        elif evidence_type == 'inspection':
            complaint.inspection_image_path = file_url
            if notes:
                complaint.inspection_notes = notes

        evidence = ComplaintEvidence(
            complaint_id=id,
            evidence_type=evidence_type,
            file_path=file_url,
            file_type=file_type,
            uploader_id=current_user.id if current_user else None,
            uploader_name=uploader_name,
            uploader_role=uploader_role,
            notes=notes
        )
        db.session.add(evidence)

        # Record StatusLog for progress
        log = StatusLog(
            complaint_id=id,
            status=complaint.status,
            previous_status=complaint.status,
            notes=f"Uploaded {evidence_type} proof photo. {notes}".strip(),
            user_id=current_user.id if current_user else None,
            user_name=uploader_name,
            user_role=uploader_role,
            timestamp=datetime.now(timezone.utc)
        )
        db.session.add(log)

        log_audit(
            action=f"EVIDENCE_UPLOADED_{evidence_type.upper()}",
            complaint_id=id,
            user=current_user,
            details=f"Uploaded {evidence_type} proof: {file_url}"
        )

        db.session.commit()
        return jsonify(evidence.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@routes_bp.route('/api/complaints/<id>/inspection', methods=['POST'])
def add_inspection(id):
    """
    Corporator or inspection authority adds inspection proof and notes.
    """
    try:
        complaint = Complaint.query.get(id)
        if not complaint:
            return jsonify({'error': 'Complaint not found'}), 404

        notes = request.form.get('notes', '').strip()
        inspection_file = request.files.get('image')
        current_user = get_current_user_from_request()

        image_url = None
        if inspection_file and inspection_file.filename:
            filename = f"INSPECT_{id}_{secure_filename(inspection_file.filename)}"
            save_path = os.path.join(UPLOAD_FOLDER, filename)
            inspection_file.save(save_path)
            image_url = f"/uploads/{filename}"
            complaint.inspection_image_path = image_url

            evidence = ComplaintEvidence(
                complaint_id=id,
                evidence_type='inspection',
                file_path=image_url,
                file_type='image',
                uploader_name=current_user.name if current_user else 'Corporator Inspector',
                uploader_role='authority',
                notes=notes
            )
            db.session.add(evidence)

        if notes:
            complaint.inspection_notes = notes

        log = StatusLog(
            complaint_id=id,
            status=complaint.status,
            previous_status=complaint.status,
            notes=f"Site inspection conducted. Notes: {notes}",
            user_name=current_user.name if current_user else 'Corporator',
            user_role='authority',
            timestamp=datetime.now(timezone.utc)
        )
        db.session.add(log)
        log_audit("SITE_INSPECTION_RECORDED", complaint_id=id, user=current_user, details=notes)

        db.session.commit()
        return jsonify(complaint.to_dict()), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# -------------------------------------------------------------
# COMMENTS SYSTEM
# -------------------------------------------------------------
@routes_bp.route('/api/complaints/<id>/comments', methods=['GET'])
def get_complaint_comments(id):
    try:
        comments = Comment.query.filter_by(complaint_id=id).order_by(Comment.created_at.asc()).all()
        return jsonify([c.to_dict() for c in comments]), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@routes_bp.route('/api/complaints/<id>/comments', methods=['POST'])
def add_complaint_comment(id):
    try:
        complaint = Complaint.query.get(id)
        if not complaint:
            return jsonify({'error': 'Complaint not found'}), 404

        data = request.json or {}
        message = data.get('message', '').strip()
        if not message:
            return jsonify({'error': 'Message cannot be empty.'}), 400

        current_user = get_current_user_from_request()
        user_name = data.get('user_name') or (current_user.name if current_user else 'Anonymous')
        user_role = data.get('user_role') or (current_user.role if current_user else 'citizen')

        new_comment = Comment(
            complaint_id=id,
            user_id=current_user.id if current_user else None,
            user_name=user_name,
            user_role=user_role,
            message=message
        )
        db.session.add(new_comment)

        log_audit(
            action="COMMENT_ADDED",
            complaint_id=id,
            user=current_user,
            details=f"Comment: {message[:60]}"
        )

        db.session.commit()
        return jsonify(new_comment.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# -------------------------------------------------------------
# IN-APP NOTIFICATIONS
# -------------------------------------------------------------
@routes_bp.route('/api/notifications', methods=['GET'])
def get_notifications():
    """
    Returns persistent in-app notifications.
    Supports user_id, user_role, ward, or recipient_email filters.
    """
    try:
        query = Notification.query
        current_user = get_current_user_from_request()

        user_id = request.args.get('user_id') or (current_user.id if current_user else None)
        user_role = request.args.get('user_role') or (current_user.role if current_user else None)
        ward = request.args.get('ward') or (current_user.ward if current_user and current_user.ward != 'all' else None)
        email = request.args.get('email') or (current_user.gmail if current_user else None)

        filters = []
        if user_id:
            filters.append(Notification.user_id == int(user_id))
        if user_role:
            filters.append(Notification.user_role == user_role)
        if ward:
            filters.append(Notification.ward == ward)
        if email:
            filters.append(Notification.recipient_email == email)

        if filters:
            from sqlalchemy import or_
            query = query.filter(or_(*filters))

        notifications = query.order_by(Notification.created_at.desc()).limit(50).all()
        unread_count = sum(1 for n in notifications if not n.is_read)

        return jsonify({
            'unread_count': unread_count,
            'notifications': [n.to_dict() for n in notifications]
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@routes_bp.route('/api/notifications/<int:id>/read', methods=['PUT'])
def mark_notification_read(id):
    try:
        notif = Notification.query.get(id)
        if not notif:
            return jsonify({'error': 'Notification not found'}), 404
        notif.is_read = True
        db.session.commit()
        return jsonify({'success': True, 'id': id}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@routes_bp.route('/api/notifications/read-all', methods=['PUT'])
def mark_all_notifications_read():
    try:
        current_user = get_current_user_from_request()
        role = request.args.get('user_role') or (current_user.role if current_user else None)
        ward = request.args.get('ward') or (current_user.ward if current_user else None)

        query = Notification.query.filter_by(is_read=False)
        if role:
            query = query.filter_by(user_role=role)
        if ward and ward != 'all':
            query = query.filter_by(ward=ward)

        for n in query.all():
            n.is_read = True
        db.session.commit()
        return jsonify({'success': True, 'message': 'All marked read.'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# -------------------------------------------------------------
# HIGHER AUTHORITY ACTIONS: REASSIGN & ADMINISTRATIVE NOTICES
# -------------------------------------------------------------
@routes_bp.route('/api/complaints/<id>/reassign', methods=['POST'])
def reassign_complaint(id):
    """
    Higher Authority reassigns complaint across wards or to a new worker, overrides priority.
    """
    try:
        complaint = Complaint.query.get(id)
        if not complaint:
            return jsonify({'error': 'Complaint not found'}), 404

        data = request.json or {}
        assigned_to = data.get('assigned_to')
        new_ward = data.get('ward')
        new_priority = data.get('priority')
        remarks = data.get('remarks', 'Administrative Reassignment by Higher Authority').strip()

        current_user = get_current_user_from_request()
        user_name = data.get('user_name') or (current_user.name if current_user else 'Higher Authority')

        if assigned_to:
            complaint.assigned_to = int(assigned_to)
            complaint.status = 'Assigned'
        if new_ward:
            complaint.ward = new_ward
        if new_priority:
            complaint.priority = new_priority

        now = datetime.now(timezone.utc)
        log = StatusLog(
            complaint_id=id,
            status=complaint.status,
            previous_status=complaint.status,
            notes=f"Administrative Reassignment: {remarks}",
            user_name=user_name,
            user_role='higher_authority',
            timestamp=now
        )
        db.session.add(log)

        log_audit(
            action="ADMINISTRATIVE_REASSIGNMENT",
            complaint_id=id,
            user=current_user,
            details=f"Reassigned to worker {assigned_to} in {new_ward or complaint.ward}. Remarks: {remarks}"
        )

        create_notification(
            title=f"Complaint {id} Reassigned",
            message=f"Higher Authority reassigned task: {remarks}",
            ward=complaint.ward,
            complaint_id=id,
            category='assignment'
        )

        db.session.commit()
        return jsonify(complaint.to_dict()), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@routes_bp.route('/api/complaints/<id>/administrative-notice', methods=['POST'])
def issue_administrative_notice(id):
    """
    Higher Authority issues an administrative notice or warning on a complaint.
    """
    try:
        complaint = Complaint.query.get(id)
        if not complaint:
            return jsonify({'error': 'Complaint not found'}), 404

        data = request.json or {}
        notice = data.get('notice', '').strip()
        notice_type = data.get('notice_type', 'warning')  # 'warning' | 'instruction' | 'inquiry'

        if not notice:
            return jsonify({'error': 'Notice content cannot be empty.'}), 400

        current_user = get_current_user_from_request()
        user_name = current_user.name if current_user else 'Higher Authority Command'

        now = datetime.now(timezone.utc)
        log = StatusLog(
            complaint_id=id,
            status=complaint.status,
            previous_status=complaint.status,
            notes=f"[{notice_type.upper()} NOTICE]: {notice}",
            user_name=user_name,
            user_role='higher_authority',
            timestamp=now
        )
        db.session.add(log)

        log_audit(
            action="ADMINISTRATIVE_NOTICE_ISSUED",
            complaint_id=id,
            user=current_user,
            details=f"Type: {notice_type}, Text: {notice}"
        )

        create_notification(
            title=f"ADMINISTRATIVE NOTICE on {id}",
            message=f"{notice_type.upper()}: {notice}",
            ward=complaint.ward,
            user_role='authority',
            complaint_id=id,
            category='escalation'
        )

        db.session.commit()
        return jsonify({'success': True, 'message': 'Notice issued.'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# -------------------------------------------------------------
# AUDIT LOGS QUERY ENDPOINT
# -------------------------------------------------------------
@routes_bp.route('/api/audit-logs', methods=['GET'])
def get_audit_logs():
    """
    Query audit trail records.
    """
    try:
        complaint_id = request.args.get('complaint_id')
        action = request.args.get('action')
        limit = int(request.args.get('limit', 100))

        query = AuditLog.query
        if complaint_id:
            query = query.filter_by(complaint_id=complaint_id)
        if action:
            query = query.filter(AuditLog.action.ilike(f"%{action}%"))

        logs = query.order_by(AuditLog.timestamp.desc()).limit(limit).all()
        return jsonify([l.to_dict() for l in logs]), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# -------------------------------------------------------------
# CORPORATOR PERFORMANCE & LEADERBOARD
# -------------------------------------------------------------
@routes_bp.route('/api/corporator/performance', methods=['GET'])
def get_corporator_performance():
    """
    Calculates corporator & ward performance purely from real DB complaint records:
    - Complaints handled
    - Total resolved & closed
    - Resolution percentage
    - Average resolution time (hours)
    - Average citizen star rating
    - Escalation count
    - Overdue count
    """
    try:
        complaints = Complaint.query.all()
        wards = ['ward_1', 'ward_2', 'ward_3']
        
        # Discover any additional wards in database
        for c in complaints:
            if c.ward and c.ward not in wards:
                wards.append(c.ward)

        leaderboard = []
        for w in wards:
            w_complaints = [c for c in complaints if c.ward == w]
            total = len(w_complaints)
            resolved_or_closed = sum(1 for c in w_complaints if c.status in ['Resolved', 'Closed'])
            resolution_rate = round((resolved_or_closed / total * 100), 1) if total > 0 else 0.0

            # Resolution times
            durations = []
            ratings = []
            for c in w_complaints:
                if c.completed_at and c.created_at:
                    durations.append((c.completed_at - c.created_at).total_seconds() / 3600.0)
                elif c.closed_at and c.created_at:
                    durations.append((c.closed_at - c.created_at).total_seconds() / 3600.0)
                if c.citizen_rating:
                    ratings.append(c.citizen_rating)

            avg_res_time = round(sum(durations) / len(durations), 1) if durations else 0.0
            avg_rating = round(sum(ratings) / len(ratings), 1) if ratings else 5.0
            escalated_cnt = sum(1 for c in w_complaints if c.escalation_flag)
            overdue_cnt = sum(1 for c in w_complaints if c.overdue_flag)

            # Find corporator user
            corporator = User.query.filter_by(role='authority', ward=w).first()
            corp_name = corporator.name if corporator else f"Ward Supervisor ({w.replace('_', ' ').title()})"

            leaderboard.append({
                'ward': w,
                'ward_name': w.replace('_', ' ').title(),
                'corporator_name': corp_name,
                'total_complaints': total,
                'resolved_count': resolved_or_closed,
                'resolution_rate': resolution_rate,
                'avg_resolution_hours': avg_res_time,
                'avg_rating': avg_rating,
                'escalated_count': escalated_cnt,
                'overdue_count': overdue_cnt
            })

        # Rank by resolution rate descending
        leaderboard.sort(key=lambda x: x['resolution_rate'], reverse=True)

        return jsonify({'leaderboard': leaderboard}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# -------------------------------------------------------------
# REPORT GENERATION & CSV EXPORT
# -------------------------------------------------------------
@routes_bp.route('/api/reports/export', methods=['GET'])
def export_complaints_report():
    """
    Generates downloadable CSV report filtered by ward, category, status, or date range.
    """
    try:
        ward = request.args.get('ward')
        category = request.args.get('category')
        status = request.args.get('status')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')

        query = Complaint.query
        if ward and ward != 'all':
            query = query.filter_by(ward=ward)
        if category:
            query = query.filter_by(category=category)
        if status:
            query = query.filter_by(status=status)
        if start_date:
            try:
                query = query.filter(Complaint.created_at >= datetime.fromisoformat(start_date))
            except ValueError:
                pass
        if end_date:
            try:
                query = query.filter(Complaint.created_at <= datetime.fromisoformat(end_date))
            except ValueError:
                pass

        complaints = query.order_by(Complaint.created_at.desc()).all()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            'Complaint ID', 'Title', 'Category', 'Priority', 'Status',
            'Ward', 'Citizen Gmail', 'Assigned Worker', 'Created At',
            'Completed At', 'Closed At', 'Escalation Level', 'Overdue Flag',
            'Citizen Rating', 'Reopen Count', 'Rejection Reason'
        ])

        for c in complaints:
            worker_name = c.assigned_worker.name if c.assigned_worker else 'Unassigned'
            writer.writerow([
                c.complaint_id,
                c.title or '',
                c.category,
                c.priority,
                c.status,
                c.ward,
                c.citizen_gmail or '',
                worker_name,
                c.created_at.isoformat() if c.created_at else '',
                c.completed_at.isoformat() if c.completed_at else '',
                c.closed_at.isoformat() if c.closed_at else '',
                c.escalation_level or 0,
                'Yes' if c.overdue_flag else 'No',
                c.citizen_rating or '',
                c.reopen_count or 0,
                c.rejection_reason or ''
            ])

        response = make_response(output.getvalue())
        response.headers['Content-Disposition'] = f"attachment; filename=smartcivic_complaints_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        response.headers['Content-Type'] = 'text/csv'
        return response
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# -------------------------------------------------------------
# USER PROFILE ENDPOINTS
# -------------------------------------------------------------
@routes_bp.route('/api/users/profile', methods=['GET'])
def get_user_profile():
    try:
        user = get_current_user_from_request()
        if not user:
            # Fallback to query param user_id
            user_id = request.args.get('user_id')
            if user_id:
                user = User.query.get(int(user_id))
        if not user:
            return jsonify({'error': 'User not authenticated'}), 401
        return jsonify(user.to_dict(include_secret=True)), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@routes_bp.route('/api/users/profile', methods=['PUT'])
def update_user_profile():
    try:
        user = get_current_user_from_request()
        data = request.json or {}
        if not user:
            user_id = data.get('user_id')
            if user_id:
                user = User.query.get(int(user_id))
        if not user:
            return jsonify({'error': 'User not authenticated'}), 401

        name = data.get('name')
        contact = data.get('contact')
        new_password = data.get('password')

        if name:
            user.name = name.strip()
        if contact:
            user.contact = contact.strip()
        if new_password and len(new_password) >= 4:
            user.password = generate_password_hash(new_password)

        db.session.commit()
        log_audit("USER_PROFILE_UPDATED", user=user, details="Profile information updated")
        return jsonify(user.to_dict(include_secret=True)), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


# -------------------------------------------------------------
# USERS & ANALYTICS
# -------------------------------------------------------------
@routes_bp.route('/api/users', methods=['GET'])
def get_users():
    try:
        role = request.args.get('role')
        ward = request.args.get('ward')
        query = User.query
        
        if role:
            query = query.filter_by(role=role)
        if ward and ward != 'all':
            query = query.filter_by(ward=ward)
            
        users = query.all()
        return jsonify([u.to_dict() for u in users]), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@routes_bp.route('/api/analytics', methods=['GET'])
def get_analytics():
    """
    Comprehensive dynamic analytics computed from database records.
    """
    try:
        query = Complaint.query
        created_after = request.args.get('created_after')
        ward_filter = request.args.get('ward')

        if ward_filter and ward_filter != 'all':
            query = query.filter_by(ward=ward_filter)

        if created_after:
            try:
                date_obj = datetime.fromisoformat(created_after)
                query = query.filter(Complaint.created_at >= date_obj)
            except ValueError:
                pass

        complaints = query.all()
        total = len(complaints)
        resolved = sum(1 for c in complaints if c.status in ['Resolved', 'Closed'])
        pending = sum(1 for c in complaints if c.status in ['Submitted', 'Verified', 'Assigned', 'In Progress'])
        escalated = sum(1 for c in complaints if c.escalation_flag or (c.escalation_level and c.escalation_level > 0))
        overdue = sum(1 for c in complaints if c.overdue_flag)
        reopened = sum(1 for c in complaints if (c.reopen_count and c.reopen_count > 0) or c.status == 'Reopened')

        resolution_rate = round((resolved / total * 100), 1) if total > 0 else 0.0

        # Calculate average resolution time
        durations = []
        for c in complaints:
            if c.completed_at and c.created_at:
                durations.append((c.completed_at - c.created_at).total_seconds() / 3600.0)
            elif c.closed_at and c.created_at:
                durations.append((c.closed_at - c.created_at).total_seconds() / 3600.0)
        avg_res_time = round(sum(durations) / len(durations), 1) if durations else 0.0

        # Dynamic category tallies
        categories = {}
        for c in complaints:
            cat = c.category or 'other'
            categories[cat] = categories.get(cat, 0) + 1

        # Dynamic status tallies
        statuses = {
            'Submitted': 0, 'Verified': 0, 'Assigned': 0,
            'In Progress': 0, 'Completed': 0, 'Resolved': 0,
            'Closed': 0, 'Rejected': 0, 'Reopened': 0
        }
        for c in complaints:
            st = c.status or 'Submitted'
            statuses[st] = statuses.get(st, 0) + 1

        # Dynamic ward tallies
        wards = {'ward_1': 0, 'ward_2': 0, 'ward_3': 0}
        for c in complaints:
            w = c.ward or 'General'
            wards[w] = wards.get(w, 0) + 1

        return jsonify({
            'total': total,
            'resolved': resolved,
            'pending': pending,
            'escalated': escalated,
            'overdue': overdue,
            'reopened': reopened,
            'resolution_rate': resolution_rate,
            'avg_resolution_hours': avg_res_time,
            'categories': categories,
            'statuses': statuses,
            'wards': wards
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# -------------------------------------------------------------
# EXOTEL IVR WEBHOOK
# -------------------------------------------------------------
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
            print(f"[IVR] Exotel SMS response ({response.status_code}): {response.text}")
        except Exception as sms_error:
            print(f"[IVR] Failed to send Exotel SMS: {str(sms_error)}")

    threading.Thread(target=_worker, daemon=True).start()

def _get_base_url():
    proto = request.headers.get('X-Forwarded-Proto', request.scheme)
    host = request.headers.get('X-Forwarded-Host') or request.headers.get('Host', request.host)
    return f"{proto}://{host}"

@routes_bp.route('/api/exotel/webhook', methods=['POST', 'GET'])
def exotel_webhook():
    try:
        raw_params = request.values.to_dict()
        digits = raw_params.get('digits') or raw_params.get('Digits') or request.args.get('digits')
        caller_phone = raw_params.get('From') or raw_params.get('CallFrom') or raw_params.get('Caller') or ''

        if digits:
            digits = str(digits).strip('"\'').strip()

        menu_choice = int(digits) if digits and digits.isdigit() else 1
        category_map = {
            1: ('pothole', 'Pothole on Main Road (Reported via Phone Call)'),
            2: ('garbage', 'Overflowing Garbage Dump (Reported via Phone Call)'),
            3: ('drainage', 'Open Sewage / Drainage Leak (Reported via Phone Call)'),
            4: ('street_light', 'Broken Street Light on Lane (Reported via Phone Call)')
        }
        category, description = category_map.get(menu_choice, ('pothole', 'Pothole on Road (Reported via Phone Call)'))

        complaint_id = f"COMP-TEL{secrets.token_hex(2).upper()}"
        ward = 'ward_1'
        latitude, longitude = 12.9716, 77.5946

        assigned_worker = User.query.filter_by(role='worker', ward=ward).first() or User.query.filter_by(role='worker').first()
        assigned_to_id = assigned_worker.id if assigned_worker else None

        new_complaint = Complaint(
            complaint_id=complaint_id,
            title=f"{category.capitalize()} (Phone Report)",
            description=f"{description} [Caller: {caller_phone}]",
            latitude=latitude,
            longitude=longitude,
            category=category,
            priority='High' if menu_choice in [1, 3] else 'Medium',
            status='Assigned' if assigned_worker else 'Submitted',
            assigned_to=assigned_to_id,
            ward=ward,
            created_at=datetime.now(timezone.utc),
            opened_at=datetime.now(timezone.utc) if assigned_worker else None,
            citizen_gmail=None
        )
        db.session.add(new_complaint)

        log = StatusLog(
            complaint_id=complaint_id,
            status='Assigned' if assigned_worker else 'Submitted',
            notes=f"Auto-created via Exotel IVR Call from {caller_phone}",
            user_name='IVR Gateway',
            user_role='system',
            timestamp=datetime.now(timezone.utc)
        )
        db.session.add(log)
        db.session.commit()

        # Send Exotel SMS if credentials present
        exotel_sid = os.getenv('EXOTEL_SID')
        exotel_key = os.getenv('EXOTEL_API_KEY')
        exotel_token = os.getenv('EXOTEL_API_TOKEN')
        exotel_subdomain = os.getenv('EXOTEL_SUBDOMAIN', 'api.exotel.com')
        exotel_caller_id = os.getenv('EXOTEL_CALLER_ID', '08047359556')

        if exotel_sid and exotel_key and exotel_token and caller_phone:
            _send_exotel_sms_async(exotel_sid, exotel_key, exotel_token, exotel_subdomain, exotel_caller_id, caller_phone, complaint_id, ward)

        return "200 OK", 200, {'Content-Type': 'text/plain'}
    except Exception as e:
        traceback.print_exc()
        return "200 OK", 200, {'Content-Type': 'text/plain'}


# -------------------------------------------------------------
# AUTHENTICATION ENDPOINTS
# -------------------------------------------------------------
@routes_bp.route('/api/auth/signup', methods=['POST'])
def signup():
    """
    Register a new user account.
    Uses Werkzeug password hashing.
    Authorities and Higher Authorities require Municipal Admin approval.
    """
    try:
        data = request.json or {}
        name = data.get('name')
        gmail = data.get('gmail')
        password = data.get('password')
        role = data.get('role')  # 'citizen' | 'worker' | 'authority' | 'higher_authority' | 'journalist'
        contact = data.get('contact')
        ward = data.get('ward', 'ward_1')

        if not name or not gmail or not password or not role or not contact:
            return jsonify({'error': 'Name, Gmail, Password, Role, and Contact are required.'}), 400

        existing_user = User.query.filter_by(gmail=gmail).first()
        if existing_user:
            return jsonify({'error': 'A user with this Gmail address already exists.'}), 409

        if role in ['authority', 'higher_authority']:
            approval_status = 'pending_approval'
            secret_key = None
        else:
            approval_status = 'approved'
            secret_key = None

        hashed_password = generate_password_hash(password)

        new_user = User(
            name=name,
            gmail=gmail,
            password=hashed_password,
            role=role,
            contact=contact,
            ward=ward if role != 'higher_authority' else 'all',
            approval_status=approval_status,
            secret_key=secret_key
        )
        db.session.add(new_user)
        db.session.commit()

        log_audit("USER_REGISTERED", user=new_user, details=f"Registered as {role} (Status: {approval_status})")

        if role in ['authority', 'higher_authority']:
            send_authority_pending_approval_email(new_user.to_dict())
        else:
            send_welcome_email(new_user.to_dict(), sender_gmail=gmail, sender_password=password)

        return jsonify(new_user.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@routes_bp.route('/api/auth/login', methods=['POST'])
def login():
    """
    Authenticate a user.
    For authorities / higher authorities, requires secret key and approved status.
    """
    try:
        data = request.json or {}
        gmail = data.get('gmail', '').strip()
        password = data.get('password', '')
        secret_key = (data.get('secret_key') or '').strip()

        if not gmail or not password:
            return jsonify({'error': 'Gmail and Password are required.'}), 400

        user = User.query.filter_by(gmail=gmail).first()
        if not user or not verify_password(user.password, password):
            return jsonify({'error': 'Invalid Gmail address or password.'}), 401

        # Authority & Higher Authority Verification
        if user.role in ['authority', 'higher_authority']:
            if user.approval_status == 'pending_approval':
                return jsonify({
                    'error': 'Your registration is awaiting Municipal Admin approval. You will receive your Secret Key via Gmail once approved.',
                    'pending_approval': True
                }), 403
            elif user.approval_status == 'rejected':
                return jsonify({'error': 'Your municipal authority registration was declined by Admin.'}), 403
            elif user.approval_status == 'suspended':
                return jsonify({'error': 'Your municipal authority account has been suspended by Admin.'}), 403

            if not secret_key:
                return jsonify({
                    'error': 'Secret Authorization Key is required for Authority login. Please enter the key sent to your Gmail.'
                }), 401

            if secret_key != (user.secret_key or '').strip():
                return jsonify({
                    'error': 'Invalid Secret Authorization Key. Please verify the key sent to your Gmail.'
                }), 401

        # Set session
        session['user_id'] = user.id
        session['user_role'] = user.role
        session['user_ward'] = user.ward

        log_audit("USER_LOGGED_IN", user=user, details="Login successful")
        return jsonify(user.to_dict(include_secret=True)), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# -------------------------------------------------------------
# MASTER MUNICIPAL ADMIN PORTAL (/admin)
# -------------------------------------------------------------
@routes_bp.route('/admin', methods=['GET'])
def admin_root():
    if session.get('is_admin'):
        return redirect('/admin/dashboard')
    return redirect('/admin/login')

@routes_bp.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'GET':
        if session.get('is_admin'):
            return redirect('/admin/dashboard')
        return render_template('admin_login.html', error=None)

    email = request.form.get('email', '').strip()
    password = request.form.get('password', '').strip()
    pin = request.form.get('pin', '').strip()

    expected_email = os.getenv('ADMIN_EMAIL', 'admin@smartcivic.ai').strip()
    expected_password = os.getenv('ADMIN_PASSWORD', 'Admin@SmartCivic2026').strip()
    expected_pin = os.getenv('ADMIN_SECRET_PIN', '7890').strip()

    if email.lower() == expected_email.lower() and password == expected_password and pin == expected_pin:
        session['is_admin'] = True
        session['admin_email'] = email
        return redirect('/admin/dashboard')
    else:
        return render_template('admin_login.html', error="Invalid Master Admin Email, Password, or Security PIN.")

@routes_bp.route('/admin/logout', methods=['GET'])
def admin_logout():
    session.clear()
    return redirect('/admin/login')

@routes_bp.route('/admin/dashboard', methods=['GET'])
@admin_required
def admin_dashboard():
    pending_authorities = User.query.filter(User.role.in_(['authority', 'higher_authority']), User.approval_status == 'pending_approval').order_by(User.created_at.desc()).all()
    active_authorities = User.query.filter(User.role.in_(['authority', 'higher_authority']), User.approval_status != 'pending_approval').order_by(User.created_at.desc()).all()
    complaints_count = Complaint.query.count()
    workers_count = User.query.filter_by(role='worker').count()
    escalations_count = Complaint.query.filter_by(escalation_flag=True).count()

    return render_template(
        'admin_dashboard.html',
        pending_authorities=pending_authorities,
        active_authorities=active_authorities,
        complaints_count=complaints_count,
        workers_count=workers_count,
        escalations_count=escalations_count
    )

@routes_bp.route('/api/admin/authorities/<int:user_id>/approve', methods=['POST'])
@admin_required
def admin_approve_authority(user_id):
    try:
        user = db.session.get(User, user_id)
        if not user or user.role not in ['authority', 'higher_authority']:
            return jsonify({'error': 'Authority user not found'}), 404

        key = generate_secret_key()
        user.secret_key = key
        user.approval_status = 'approved'
        user.approved_at = datetime.now(timezone.utc)
        db.session.commit()

        send_authority_approval_email(user.to_dict(include_secret=True), key)
        return jsonify({'success': True, 'secret_key': key, 'user': user.to_dict(include_secret=True)}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@routes_bp.route('/api/admin/authorities/<int:user_id>/reject', methods=['POST'])
@admin_required
def admin_reject_authority(user_id):
    try:
        user = db.session.get(User, user_id)
        if not user or user.role not in ['authority', 'higher_authority']:
            return jsonify({'error': 'Authority user not found'}), 404

        data = request.json or {}
        reason = data.get('reason', 'Administrative decision.')
        user.approval_status = 'rejected'
        user.secret_key = None
        db.session.commit()

        send_authority_rejection_email(user.to_dict(), reason)
        return jsonify({'success': True, 'message': 'Registration rejected.'}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@routes_bp.route('/api/admin/authorities/<int:user_id>/regenerate-key', methods=['POST'])
@admin_required
def admin_regenerate_key(user_id):
    try:
        user = db.session.get(User, user_id)
        if not user or user.role not in ['authority', 'higher_authority']:
            return jsonify({'error': 'Authority user not found'}), 404

        new_key = generate_secret_key()
        user.secret_key = new_key
        db.session.commit()

        send_authority_key_regenerated_email(user.to_dict(include_secret=True), new_key)
        return jsonify({'success': True, 'secret_key': new_key}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@routes_bp.route('/api/admin/authorities/<int:user_id>/toggle-status', methods=['POST'])
@admin_required
def admin_toggle_authority_status(user_id):
    try:
        user = db.session.get(User, user_id)
        if not user or user.role not in ['authority', 'higher_authority']:
            return jsonify({'error': 'Authority user not found'}), 404

        data = request.json or {}
        action = data.get('action')
        if action == 'suspend':
            user.approval_status = 'suspended'
        elif action == 'reactivate':
            user.approval_status = 'approved'

        db.session.commit()
        return jsonify({'success': True, 'status': user.approval_status}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@routes_bp.route('/api/admin/pending-count', methods=['GET'])
def admin_pending_count():
    try:
        count = User.query.filter(User.role.in_(['authority', 'higher_authority']), User.approval_status == 'pending_approval').count()
        return jsonify({'pending_count': count}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# -------------------------------------------------------------
# JOURNALIST REPORTS ENDPOINTS
# -------------------------------------------------------------
@routes_bp.route('/api/journalist/reports/generate', methods=['POST'])
def generate_journalist_report():
    try:
        data = request.json or {}
        complaint_id = data.get('complaint_id')
        if not complaint_id:
            return jsonify({'error': 'Complaint ID is required'}), 400

        complaint = Complaint.query.get(complaint_id)
        if not complaint:
            return jsonify({'error': 'Complaint not found'}), 404

        category_title = complaint.category.replace('_', ' ').upper()
        title = f"INVESTIGATIVE REPORT: Unaddressed {category_title} Neglect in Smart City Ward"
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
            content += f"COMPUTER VISION AUDIT REPORT:\nAdvanced image telemetry scans: {complaint.image_analysis}\n\n"

        content += (
            f"PRESS WATCHDOG VERDICT:\n"
            f"Flagged for public press release due to administrative inaction. "
            f"Immediate municipal intervention required."
        )

        return jsonify({'complaint_id': complaint_id, 'title': title, 'content': content}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@routes_bp.route('/api/journalist/reports', methods=['POST'])
def save_journalist_report():
    try:
        data = request.json or {}
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
        data = request.json or {}
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
        return jsonify(report.to_dict()), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# -------------------------------------------------------------
# HUGGING FACE MULTILINGUAL AI ENDPOINTS
# -------------------------------------------------------------
@routes_bp.route('/api/ai/translate', methods=['POST'])
def ai_translate_endpoint():
    """
    Translates text between English, Kannada (kn), Hindi (hi), and Telugu (te)
    using Hugging Face Multilingual AI.
    """
    try:
        data = request.json or {}
        text = data.get('text', '').strip()
        source_lang = data.get('source_lang', 'auto').strip().lower()
        target_lang = data.get('target_lang', 'en').strip().lower()

        if not text:
            return jsonify({'error': 'Missing required parameter: text'}), 400

        result = translate_text(text, source_lang=source_lang, target_lang=target_lang)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({'error': f"Translation error: {str(e)}"}), 500

@routes_bp.route('/api/ai/classify-multilingual', methods=['POST'])
def ai_classify_multilingual_endpoint():
    """
    Multilingual civic issue classification powered by Hugging Face AI.
    Accurately categorizes and priorities complaints in Kannada, Hindi, Telugu, or English.
    """
    try:
        data = request.json or {}
        text = data.get('text') or data.get('description', '')
        title = data.get('title', '')
        if not text:
            return jsonify({'error': 'Missing required parameter: text or description'}), 400

        result = classify_complaint_multilingual(text, title=title)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({'error': f"Multilingual classification error: {str(e)}"}), 500

@routes_bp.route('/api/ai/detect-language', methods=['POST'])
def ai_detect_language_endpoint():
    """
    High-speed script and language detector for Indic languages and English.
    """
    try:
        data = request.json or {}
        text = data.get('text', '')
        lang = detect_language(text)
        return jsonify({
            'language': lang,
            'language_code': lang,
            'language_name': SUPPORTED_LANGUAGES.get(lang, 'English')
        }), 200
    except Exception as e:
        return jsonify({'error': f"Language detection error: {str(e)}"}), 500

@routes_bp.route('/api/ai/languages', methods=['GET'])
def ai_get_supported_languages():
    return jsonify(SUPPORTED_LANGUAGES), 200

