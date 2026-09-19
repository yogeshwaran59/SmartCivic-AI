import os
import unittest
from datetime import datetime, timedelta, timezone
from PIL import Image
from app import create_app
from models import db, Complaint, User, StatusLog
from ai_processor import get_image_similarity, classify_complaint_text, haversine_distance
from scheduler import run_escalation_checks

class TestSmartCivicAI(unittest.TestCase):
    def setUp(self):
        # Use a separate SQLite database for verification testing
        db_path = os.path.join(os.path.dirname(__file__), 'test_smartcivic.db')

        # Configure app for testing
        self.app = create_app({
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}'
        })
        self.client = self.app.test_client()
        
        with self.app.app_context():
            db.drop_all()
            db.create_all()
            
            # Seed test supervisor and workers
            test_supervisor = User(
                id=1, 
                name="Supervisor Suresh", 
                role="authority", 
                contact="+15550100001", 
                ward="ward_1",
                gmail="suresh@gmail.com",
                password="password",
                approval_status="approved",
                secret_key="AUTH-TEST-KEY1"
            )
            test_supervisor2 = User(
                id=2, 
                name="Supervisor Priya", 
                role="authority", 
                contact="+15550100003", 
                ward="ward_2",
                gmail="priya@gmail.com",
                password="password",
                approval_status="approved",
                secret_key="AUTH-TEST-KEY2"
            )
            test_worker = User(
                id=4, 
                name="Worker Ramesh", 
                role="worker", 
                contact="+15550100002", 
                ward="ward_1",
                gmail="ramesh@gmail.com",
                password="password",
                approval_status="approved"
            )
            test_worker2 = User(
                id=5, 
                name="Worker Dinesh", 
                role="worker", 
                contact="+15550100004", 
                ward="ward_2",
                gmail="dinesh@gmail.com",
                password="password",
                approval_status="approved"
            )
            db.session.add(test_supervisor)
            db.session.add(test_supervisor2)
            db.session.add(test_worker)
            db.session.add(test_worker2)
            db.session.commit()

        # Create dummy images for similarity and description test
        self.img1_path = os.path.join(os.path.dirname(__file__), 'test_red1.jpg')
        self.img2_path = os.path.join(os.path.dirname(__file__), 'test_red2.jpg')
        self.img3_path = os.path.join(os.path.dirname(__file__), 'test_blue.jpg')
        
        # Red Image 1
        img1 = Image.new('RGB', (100, 100), color='red')
        img1.save(self.img1_path)
        # Red Image 2 (nearly identical color values)
        img2 = Image.new('RGB', (100, 100), color=(250, 0, 0))
        img2.save(self.img2_path)
        # Blue Image (completely different)
        img3 = Image.new('RGB', (100, 100), color='blue')
        img3.save(self.img3_path)

    def tearDown(self):
        # Clean up database file
        db_path = os.path.join(os.path.dirname(__file__), 'test_smartcivic.db')
        if os.path.exists(db_path):
            try:
                os.remove(db_path)
            except PermissionError:
                pass
                
        # Clean up images
        for p in [self.img1_path, self.img2_path, self.img3_path]:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except PermissionError:
                    pass

    def test_ai_heuristics(self):
        # Test text keyword heuristic parser
        cat, prio = classify_complaint_text("There is a large pothole on the main highway, very dangerous")
        self.assertEqual(cat, 'pothole')
        self.assertEqual(prio, 'High')
        
        cat, prio = classify_complaint_text("Stinky garbage pile overflowing and blocking street corner")
        self.assertEqual(cat, 'garbage')
        self.assertEqual(prio, 'Medium')

        cat, prio = classify_complaint_text("Street lights are dark and broken on the road")
        self.assertEqual(cat, 'street_light')
        self.assertEqual(prio, 'Medium')

    def test_image_similarity(self):
        # Red1 and Red2 should have very high similarity
        sim_high = get_image_similarity(self.img1_path, self.img2_path)
        self.assertTrue(sim_high > 0.82)
        
        # Red1 and Blue should have very low similarity
        sim_low = get_image_similarity(self.img1_path, self.img3_path)
        self.assertTrue(sim_low < 0.5)

    def test_duplicate_and_ward_assignment(self):
        # Submit a complaint (lat=12.98, lng=77.58) -> Ward 1
        with open(self.img1_path, 'rb') as img:
            response = self.client.post('/api/complaints', data={
                'description': 'Pothole on standard lane',
                'latitude': '12.980000',
                'longitude': '77.580000',
                'contact': '+15559990001',
                'image': img
            })
        self.assertEqual(response.status_code, 201)
        data = response.get_json()
        comp1_id = data['complaint_id']
        self.assertEqual(data['ward'], 'ward_1')
        self.assertEqual(data['is_duplicate'], False)
        # Check that image description analysis was executed
        self.assertIsNotNone(data['image_analysis'])
        self.assertTrue("analyzed" in data['image_analysis'])

        # Submit duplicate complaint 10 meters away with same image
        with open(self.img2_path, 'rb') as img:
            response = self.client.post('/api/complaints', data={
                'description': 'Crater pothole on lane',
                'latitude': '12.980050',
                'longitude': '77.580000',
                'contact': '+15559990002',
                'image': img
            })
        self.assertEqual(response.status_code, 201)
        data = response.get_json()
        self.assertEqual(data['is_duplicate'], True)
        self.assertEqual(data['duplicate_of'], comp1_id)

    def test_gmail_notifications_and_tracking(self):
        # 1. Post a complaint with gmail address
        response = self.client.post('/api/complaints', data={
            'description': 'Drainage overflow near bus stop',
            'latitude': '12.972000',
            'longitude': '77.595000',
            'contact': '+15559993333',
            'gmail': 'citizen.test@gmail.com'
        })
        self.assertEqual(response.status_code, 201)
        data = response.get_json()
        comp_id = data['complaint_id']
        self.assertEqual(data['citizen_gmail'], 'citizen.test@gmail.com')

        # 2. Track complaint by ID
        get_res = self.client.get(f'/api/complaints/{comp_id}')
        self.assertEqual(get_res.status_code, 200)
        track_data = get_res.get_json()
        self.assertEqual(track_data['complaint_id'], comp_id)
        self.assertEqual(track_data['citizen_gmail'], 'citizen.test@gmail.com')

        # 3. Update status (e.g. Assigned to worker)
        put_res = self.client.put(f'/api/complaints/{comp_id}', json={
            'status': 'Assigned',
            'assigned_to': 4,
            'notes': 'Worker Ramesh dispatched to clear drainage'
        })
        self.assertEqual(put_res.status_code, 200)
        put_data = put_res.get_json()
        self.assertEqual(put_data['status'], 'Assigned')

    def test_scheduler_escalation(self):
        with self.app.app_context():
            # Create a mock complaint
            comp = Complaint(
                complaint_id="COMP-OLD1",
                description="Street light out",
                latitude=12.98,
                longitude=77.58,
                category="street_light",
                priority="Medium",
                status="Submitted",
                created_at=datetime.now(timezone.utc) - timedelta(hours=49),
                escalation_flag=False,
                ward="ward_1"
            )
            db.session.add(comp)
            db.session.commit()
            
            # Run escalation checks
            run_escalation_checks(self.app)
            
            # Fetch updated complaint
            updated_comp = db.session.get(Complaint, "COMP-OLD1")
            self.assertIsNotNone(updated_comp)
            assert updated_comp is not None
            self.assertEqual(updated_comp.escalation_flag, True)
            self.assertEqual(updated_comp.status, "Assigned")
            self.assertEqual(updated_comp.assigned_to, 1) # Assigned to supervisor Suresh (Ward 1)

    def test_user_authentication(self):
        # 1. Sign up new citizen user
        response = self.client.post('/api/auth/signup', json={
            'name': 'Citizen Charlie',
            'gmail': 'charlie@gmail.com',
            'password': 'secretpassword',
            'role': 'citizen',
            'contact': '+15557770001',
            'ward': 'ward_2'
        })
        self.assertEqual(response.status_code, 201)
        data = response.get_json()
        self.assertEqual(data['name'], 'Citizen Charlie')
        self.assertEqual(data['gmail'], 'charlie@gmail.com')

        # Try to sign up again (conflict email)
        response_dup = self.client.post('/api/auth/signup', json={
            'name': 'Duplicate Charlie',
            'gmail': 'charlie@gmail.com',
            'password': 'newpassword',
            'role': 'citizen',
            'contact': '+15557770002',
            'ward': 'ward_2'
        })
        self.assertEqual(response_dup.status_code, 409)

        # 2. Login with correct credentials
        response_login = self.client.post('/api/auth/login', json={
            'gmail': 'charlie@gmail.com',
            'password': 'secretpassword'
        })
        self.assertEqual(response_login.status_code, 200)
        login_data = response_login.get_json()
        self.assertEqual(login_data['role'], 'citizen')

        # 3. Login with wrong credentials
        response_fail = self.client.post('/api/auth/login', json={
            'gmail': 'charlie@gmail.com',
            'password': 'wrongpassword'
        })
        self.assertEqual(response_fail.status_code, 401)

    def test_journalist_redirection_and_reports(self):
        with self.app.app_context():
            # Seed a complaint created 6 minutes ago, unopened (opened_at is None, status is Submitted)
            comp = Complaint(
                complaint_id="COMP-J1",
                description="Damaged footpath safety hazard",
                latitude=12.97,
                longitude=77.59,
                category="other",
                priority="Medium",
                status="Submitted",
                created_at=datetime.now(timezone.utc) - timedelta(minutes=6),
                redirected_to_journalist=False,
                ward="ward_3"
            )
            db.session.add(comp)
            db.session.commit()

            # Run scheduler background check
            run_escalation_checks(self.app)

            # Check redirection state in database
            updated_comp = db.session.get(Complaint, "COMP-J1")
            self.assertIsNotNone(updated_comp)
            assert updated_comp is not None
            self.assertEqual(updated_comp.redirected_to_journalist, True)

            # Test GET /api/complaints?redirected_to_journalist=true
            response = self.client.get('/api/complaints?redirected_to_journalist=true')
            self.assertEqual(response.status_code, 200)
            list_data = response.get_json()
            self.assertTrue(any(c['complaint_id'] == 'COMP-J1' for c in list_data))

            # Test AI generation endpoint POST /api/journalist/reports/generate
            gen_response = self.client.post('/api/journalist/reports/generate', json={
                'complaint_id': 'COMP-J1'
            })
            self.assertEqual(gen_response.status_code, 200)
            gen_data = gen_response.get_json()
            self.assertIn('title', gen_data)
            self.assertIn('content', gen_data)
            self.assertEqual(gen_data['complaint_id'], 'COMP-J1')

            # Test POST /api/journalist/reports
            save_response = self.client.post('/api/journalist/reports', json={
                'complaint_id': 'COMP-J1',
                'title': gen_data['title'],
                'content': gen_data['content'],
                'published': False
            })
            self.assertEqual(save_response.status_code, 201)
            saved_data = save_response.get_json()
            self.assertEqual(saved_data['published'], False)

            # Test PUT /api/journalist/reports/<id> to publish it
            report_id = saved_data['id']
            pub_response = self.client.put(f'/api/journalist/reports/{report_id}', json={
                'published': True
            })
            self.assertEqual(pub_response.status_code, 200)
            pub_data = pub_response.get_json()
            self.assertEqual(pub_data['published'], True)

            # Test GET /api/journalist/reports
            get_response = self.client.get('/api/journalist/reports')
            self.assertEqual(get_response.status_code, 200)
            reports_list = get_response.get_json()
            self.assertTrue(any(r['id'] == report_id for r in reports_list))

    def test_geotag_parsing_endpoint(self):
        # Test parse geotag endpoint with image
        with open(self.img1_path, 'rb') as img:
            response = self.client.post('/api/parse-geotag', data={
                'image': img,
                'description': 'Lat 12.980000 Long 77.580000 photo test'
            })
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['found'])
        self.assertAlmostEqual(data['latitude'], 12.98, places=3)
        self.assertAlmostEqual(data['longitude'], 77.58, places=3)
        self.assertEqual(data['ward'], 'ward_1')

    def test_heatmap_and_analytics(self):
        # 1. Heatmap summary endpoint
        hm_res = self.client.get('/api/heatmap/summary')
        self.assertEqual(hm_res.status_code, 200)
        hm_data = hm_res.get_json()
        self.assertIn('regional_summary', hm_data)
        self.assertIn('heat_points', hm_data)

        # 2. Analytics endpoint
        an_res = self.client.get('/api/analytics')
        self.assertEqual(an_res.status_code, 200)
        an_data = an_res.get_json()
        self.assertIn('total', an_data)
        self.assertIn('categories', an_data)
        self.assertIn('statuses', an_data)
        self.assertIn('wards', an_data)

    def test_users_filtering(self):
        # Test filtering users by role
        users_res = self.client.get('/api/users?role=worker')
        self.assertEqual(users_res.status_code, 200)
        users = users_res.get_json()
        self.assertTrue(all(u['role'] == 'worker' for u in users))

        # Test filtering users by ward
        ward_users_res = self.client.get('/api/users?ward=ward_1')
        self.assertEqual(ward_users_res.status_code, 200)
        ward_users = ward_users_res.get_json()
        self.assertTrue(all(u['ward'] == 'ward_1' for u in ward_users))

    def test_authority_approval_and_admin_workflow(self):
        # 1. Authority signs up -> should be pending approval
        signup_res = self.client.post('/api/auth/signup', json={
            'name': 'Officer Vikram',
            'gmail': 'vikram.authority@gmail.com',
            'password': 'officerpassword',
            'role': 'authority',
            'contact': '+15558880001',
            'ward': 'ward_1'
        })
        self.assertEqual(signup_res.status_code, 201)
        auth_data = signup_res.get_json()
        auth_id = auth_data['id']
        self.assertEqual(auth_data['approval_status'], 'pending_approval')
        self.assertFalse(auth_data['has_secret_key'])

        # 2. Authority attempts to log in before approval -> should be 403 Forbidden
        login_fail = self.client.post('/api/auth/login', json={
            'gmail': 'vikram.authority@gmail.com',
            'password': 'officerpassword'
        })
        self.assertEqual(login_fail.status_code, 403)
        self.assertTrue(login_fail.get_json().get('pending_approval'))

        # 3. Check pending count
        count_res = self.client.get('/api/admin/pending-count')
        self.assertEqual(count_res.status_code, 200)
        self.assertGreaterEqual(count_res.get_json()['pending_count'], 1)

        # 4. Admin logs in with session
        with self.client.session_transaction() as sess:
            sess['is_admin'] = True

        # 5. Admin approves authority
        approve_res = self.client.post(f'/api/admin/authorities/{auth_id}/approve')
        self.assertEqual(approve_res.status_code, 200)
        app_data = approve_res.get_json()
        self.assertTrue(app_data['success'])
        secret_key = app_data['secret_key']
        self.assertTrue(secret_key.startswith('AUTH-'))

        # 6. Authority logs in with wrong secret key -> 401
        login_wrong_key = self.client.post('/api/auth/login', json={
            'gmail': 'vikram.authority@gmail.com',
            'password': 'officerpassword',
            'secret_key': 'WRONG-KEY-XYZ'
        })
        self.assertEqual(login_wrong_key.status_code, 401)

        # 7. Authority logs in with correct secret key -> 200 Success
        login_ok = self.client.post('/api/auth/login', json={
            'gmail': 'vikram.authority@gmail.com',
            'password': 'officerpassword',
            'secret_key': secret_key
        })
        self.assertEqual(login_ok.status_code, 200)
        user_logged = login_ok.get_json()
        self.assertEqual(user_logged['role'], 'authority')
        self.assertEqual(user_logged['approval_status'], 'approved')

        # 8. Authority logs in again with the SAME key -> 200 Success
        login_again = self.client.post('/api/auth/login', json={
            'gmail': 'vikram.authority@gmail.com',
            'password': 'officerpassword',
            'secret_key': secret_key
        })
        self.assertEqual(login_again.status_code, 200)

        # 9. Admin regenerates key
        regen_res = self.client.post(f'/api/admin/authorities/{auth_id}/regenerate-key')
        self.assertEqual(regen_res.status_code, 200)
        new_secret_key = regen_res.get_json()['secret_key']
        self.assertNotEqual(secret_key, new_secret_key)

        # Old key fails
        login_old_key = self.client.post('/api/auth/login', json={
            'gmail': 'vikram.authority@gmail.com',
            'password': 'officerpassword',
            'secret_key': secret_key
        })
        self.assertEqual(login_old_key.status_code, 401)

        # New key succeeds
        login_new_ok = self.client.post('/api/auth/login', json={
            'gmail': 'vikram.authority@gmail.com',
            'password': 'officerpassword',
            'secret_key': new_secret_key
        })
        self.assertEqual(login_new_ok.status_code, 200)

        # 10. Admin suspends authority
        suspend_res = self.client.post(f'/api/admin/authorities/{auth_id}/toggle-status', json={'action': 'suspend'})
        self.assertEqual(suspend_res.status_code, 200)
        self.assertEqual(suspend_res.get_json()['status'], 'suspended')

        # Suspended login fails with 403
        login_suspended = self.client.post('/api/auth/login', json={
            'gmail': 'vikram.authority@gmail.com',
            'password': 'officerpassword',
            'secret_key': new_secret_key
        })
        self.assertEqual(login_suspended.status_code, 403)

    def test_admin_portal_routes(self):
        # 1. Access /admin without login -> redirect to /admin/login
        res_redir = self.client.get('/admin')
        self.assertEqual(res_redir.status_code, 302)
        self.assertIn('/admin/login', res_redir.headers['Location'])

        # 2. Access /admin/login GET -> 200 HTML page
        res_login_page = self.client.get('/admin/login')
        self.assertEqual(res_login_page.status_code, 200)
        self.assertIn(b'Municipal Admin Portal', res_login_page.data)

        # 3. Post invalid login -> returns error
        res_bad_login = self.client.post('/admin/login', data={
            'email': 'wrong@admin.com',
            'password': 'badpassword',
            'pin': '0000'
        })
        self.assertEqual(res_bad_login.status_code, 200)
        self.assertIn(b'Invalid Master Admin', res_bad_login.data)

        # 4. Post valid admin login -> redirects to dashboard
        res_good_login = self.client.post('/admin/login', data={
            'email': 'admin@smartcivic.ai',
            'password': 'Admin@SmartCivic2026',
            'pin': '7890'
        })
        self.assertEqual(res_good_login.status_code, 302)
        self.assertIn('/admin/dashboard', res_good_login.headers['Location'])

        # 5. Access dashboard with session
        res_dash = self.client.get('/admin/dashboard')
        self.assertEqual(res_dash.status_code, 200)
        self.assertIn(b'Municipal Administration Command Control', res_dash.data)

        # 6. Logout
        res_logout = self.client.get('/admin/logout')
        self.assertEqual(res_logout.status_code, 302)

    def test_enhanced_civic_management_features(self):
        """
        Tests the complete civic issue management lifecycle:
        Rejection, Evidence uploads, Citizen verification, Reopening,
        Comments, In-app notifications, Audit logs, Performance leaderboard,
        CSV export, Higher authority reassignments, and Profile management.
        """
        # 1. Create a test complaint
        res = self.client.post('/api/complaints', data={
            'title': 'Dangerous Pothole on Main Road',
            'description': 'Deep crater pothole near intersection causing severe hazard',
            'latitude': '12.980000',
            'longitude': '77.580000',
            'contact': '+15559998888',
            'gmail': 'anita.citizen@gmail.com',
            'category': 'pothole',
            'priority': 'High'
        })
        self.assertEqual(res.status_code, 201)
        comp_data = res.get_json()
        cid = comp_data['complaint_id']
        self.assertEqual(comp_data['title'], 'Dangerous Pothole on Main Road')
        self.assertEqual(comp_data['priority'], 'High')

        # 1b. Test Corporator / Authority Verification
        # Cross-ward corporator (Ward 2) cannot verify Ward 1 complaint -> 403
        unauth_verify = self.client.post(f'/api/complaints/{cid}/verify', headers={'X-User-Id': '2'})
        self.assertEqual(unauth_verify.status_code, 403)

        # Authorized ward corporator (Ward 1) successfully verifies
        verify_res = self.client.post(f'/api/complaints/{cid}/verify', headers={'X-User-Id': '1'})
        self.assertEqual(verify_res.status_code, 200)
        self.assertEqual(verify_res.get_json()['status'], 'Verified')

        # 1c. Test Invalid Lifecycle Transition (e.g. Verified -> Closed is forbidden)
        bad_trans = self.client.put(f'/api/complaints/{cid}', json={'status': 'Closed'})
        self.assertEqual(bad_trans.status_code, 400)

        # 1d. Test Worker Authorization (Worker 5 Dinesh cannot modify Ramesh's task)
        unauth_worker = self.client.put(f'/api/complaints/{cid}', json={
            'status': 'In Progress',
            'notes': 'Unauthorized modification attempt'
        }, headers={'X-User-Id': '5'})
        self.assertEqual(unauth_worker.status_code, 403)

        # 2. Test Multi-stage Evidence Upload (Before-work & Progress)
        with open(self.img1_path, 'rb') as img:
            ev_res = self.client.post(f'/api/complaints/{cid}/evidence', data={
                'image': img,
                'evidence_type': 'before',
                'notes': 'Site inspected before starting asphalt work',
                'uploader_name': 'Worker Ramesh',
                'uploader_role': 'worker'
            })
        self.assertEqual(ev_res.status_code, 201)
        ev_data = ev_res.get_json()
        self.assertEqual(ev_data['evidence_type'], 'before')

        # 3. Test Progress notes and state transition to In Progress
        put_prog = self.client.put(f'/api/complaints/{cid}', json={
            'status': 'In Progress',
            'notes': 'Asphalt mixer arrived, excavating edge',
            'user_name': 'Worker Ramesh',
            'user_role': 'worker'
        })
        self.assertEqual(put_prog.status_code, 200)
        self.assertEqual(put_prog.get_json()['status'], 'In Progress')

        # 4. Test Comments System
        com_post = self.client.post(f'/api/complaints/{cid}/comments', json={
            'message': 'Work is progressing steadily. Should finish by evening.',
            'user_name': 'Worker Ramesh',
            'user_role': 'worker'
        })
        self.assertEqual(com_post.status_code, 201)
        com_get = self.client.get(f'/api/complaints/{cid}/comments')
        self.assertEqual(com_get.status_code, 200)
        self.assertEqual(len(com_get.get_json()), 1)

        # 5. Worker completes work with Resolution Photo
        with open(self.img2_path, 'rb') as img:
            res_put = self.client.put(f'/api/complaints/{cid}', data={
                'status': 'Completed',
                'resolution_image': img,
                'notes': 'Pothole filled with heavy-duty cold mix and compacted level',
                'user_name': 'Worker Ramesh',
                'user_role': 'worker'
            })
        self.assertEqual(res_put.status_code, 200)
        self.assertEqual(res_put.get_json()['status'], 'Completed')

        # 6. Citizen Verification: Reject & Reopen with mandatory reason
        rej_res = self.client.post(f'/api/complaints/{cid}/verify-resolution', json={
            'action': 'reject',
            'reason': 'The surface is uneven and gravel is still scattered',
            'rating': 2,
            'user_name': 'Citizen Anita'
        })
        self.assertEqual(rej_res.status_code, 200)
        rej_data = rej_res.get_json()
        self.assertEqual(rej_data['status'], 'Reopened')
        self.assertEqual(rej_data['reopen_count'], 1)

        # 7. Worker refines and Marks Completed Again
        with open(self.img2_path, 'rb') as img:
            res_put2 = self.client.put(f'/api/complaints/{cid}', data={
                'status': 'Completed',
                'resolution_image': img,
                'notes': 'Surface smoothed with fine layer asphalt',
                'user_name': 'Worker Ramesh',
                'user_role': 'worker'
            })
        self.assertEqual(res_put2.status_code, 200)

        # 8. Citizen Verification: Accept & Close with 5 Stars
        acc_res = self.client.post(f'/api/complaints/{cid}/verify-resolution', json={
            'action': 'accept',
            'rating': 5,
            'satisfaction': 'satisfactory',
            'feedback': 'Excellent clean finish! Thank you.',
            'user_name': 'Citizen Anita'
        })
        self.assertEqual(acc_res.status_code, 200)
        acc_data = acc_res.get_json()
        self.assertEqual(acc_data['status'], 'Closed')
        self.assertEqual(acc_data['citizen_rating'], 5)

        # 9. Test Rejection flow on another complaint with mandatory reason
        res2 = self.client.post('/api/complaints', data={
            'description': 'Commercial dispute about banner on private fence',
            'latitude': '12.980000',
            'longitude': '77.580000',
            'contact': '+15559991111',
            'category': 'other'
        })
        cid2 = res2.get_json()['complaint_id']

        # Missing reason fails
        fail_rej = self.client.post(f'/api/complaints/{cid2}/reject', json={})
        self.assertEqual(fail_rej.status_code, 400)

        # Successful rejection
        succ_rej = self.client.post(f'/api/complaints/{cid2}/reject', json={
            'rejection_reason': 'Private civil matter; outside municipal jurisdiction.'
        })
        self.assertEqual(succ_rej.status_code, 200)
        self.assertEqual(succ_rej.get_json()['status'], 'Rejected')

        # 10. Test In-App Notifications
        notifs_res = self.client.get('/api/notifications?ward=ward_1')
        self.assertEqual(notifs_res.status_code, 200)
        notifs_data = notifs_res.get_json()
        self.assertIn('notifications', notifs_data)
        self.assertGreaterEqual(len(notifs_data['notifications']), 1)

        # Mark all read
        read_all_res = self.client.put('/api/notifications/read-all?ward=ward_1')
        self.assertEqual(read_all_res.status_code, 200)

        # 11. Test Audit Logs
        audit_res = self.client.get(f'/api/audit-logs?complaint_id={cid}')
        self.assertEqual(audit_res.status_code, 200)
        logs = audit_res.get_json()
        self.assertGreaterEqual(len(logs), 2)

        # 12. Test Corporator Performance Leaderboard
        perf_res = self.client.get('/api/corporator/performance')
        self.assertEqual(perf_res.status_code, 200)
        perf_data = perf_res.get_json()
        self.assertIn('leaderboard', perf_data)
        self.assertGreaterEqual(len(perf_data['leaderboard']), 3)

        # 13. Test CSV Report Export
        csv_res = self.client.get('/api/reports/export?ward=ward_1')
        self.assertEqual(csv_res.status_code, 200)
        self.assertEqual(csv_res.headers['Content-Type'], 'text/csv')
        self.assertIn(b'Complaint ID,Title,Category', csv_res.data)

        # 14. Test Higher Authority Reassign and Notice
        notice_res = self.client.post(f'/api/complaints/{cid}/administrative-notice', json={
            'notice': 'Ensure quarterly review of road joints',
            'notice_type': 'instruction'
        })
        self.assertEqual(notice_res.status_code, 200)

        # 15. Test User Profile View and Update
        prof_get = self.client.get('/api/users/profile?user_id=1')
        self.assertEqual(prof_get.status_code, 200)
        self.assertEqual(prof_get.get_json()['name'], 'Supervisor Suresh')

        prof_put = self.client.put('/api/users/profile', json={
            'user_id': 1,
            'name': 'Supervisor Suresh V2',
            'contact': '+919999988888'
        })
        self.assertEqual(prof_put.status_code, 200)
        self.assertEqual(prof_put.get_json()['name'], 'Supervisor Suresh V2')

if __name__ == '__main__':
    unittest.main()

