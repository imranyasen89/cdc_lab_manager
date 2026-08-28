import unittest
from datetime import datetime, date, timedelta
import os
from app import create_app, db
from app.models import User, Branch, StaffProfile, StaffPerformanceReport

class StaffReportsTestCase(unittest.TestCase):
    def setUp(self):
        # Force SQLAlchemy to use isolated in-memory DB for tests
        self.old_db_url = os.environ.get('DATABASE_URL')
        os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
        
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.app_context = self.app.app_context()
        self.app_context.push()
        
        db.create_all()
        self.seed_test_data()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()
        
        if self.old_db_url is not None:
            os.environ['DATABASE_URL'] = self.old_db_url
        else:
            os.environ.pop('DATABASE_URL', None)

    def seed_test_data(self):
        # Branch
        self.branch = Branch(name="G-11 Hub", code="G11", latitude=33.6822, longitude=73.0076)
        db.session.add(self.branch)
        
        # Users
        self.admin = User(name="Admin User", username="admin", employee_id="EMP-1", role="ADMIN", status=True)
        self.staff = User(name="Lab Staff Member", username="labstaff", employee_id="EMP-100", role="LAB_STAFF", status=True, branch=self.branch)
        
        for u in [self.admin, self.staff]:
            u.set_password("pass123")
            db.session.add(u)
            
        db.session.commit()

        # Assign STAFF_WORKSPACE permission to staff user
        from app.models import UserTaskPermission
        tp = UserTaskPermission(user_id=self.staff.id, permission='STAFF_WORKSPACE')
        db.session.add(tp)
        db.session.commit()

        # Initial Staff Profile
        self.profile = StaffProfile(
            user_id=self.staff.id,
            designation="Phlebotomist",
            overall_experience=3.5,
            cdc_experience=1.5,
            qualification="BS MLT",
            sections_independent="Phlebotomy, Hematology",
            study_further="Yes",
            research_interest="No",
            training_requested="Molecular diagnostics"
        )
        db.session.add(self.profile)
        db.session.commit()

    def test_staff_dashboard_view(self):
        with self.app.test_client() as client:
            with client.session_transaction() as sess:
                sess['_user_id'] = str(self.staff.id)
                sess['_fresh'] = True
                
            response = client.get('/reports/staff/dashboard')
            self.assertEqual(response.status_code, 200)
            html = response.data.decode('utf-8')
            self.assertIn('Staff Performance Workspace', html)
            self.assertIn('BS MLT', html)
            self.assertIn('Phlebotomy', html)
            self.assertIn('Hematology', html)

    def test_staff_submit_daily_report(self):
        with self.app.test_client() as client:
            with client.session_transaction() as sess:
                sess['_user_id'] = str(self.staff.id)
                sess['_fresh'] = True
                
            response = client.post('/reports/staff/submit', data={
                'duty_status': 'Present',
                'shift': 'Evening',
                'branch_id': str(self.branch.id),
                'sections': ['Chemistry', 'Hematology'],
                'patients_booked': '10',
                'samples_collected': '12',
                'tests_processed': '45',
                'results_entered': '45',
                'samples_referred': '2',
                'pending_work': '5',
                'qc_issue': 'true',
                'qc_details': 'Instrument calibration error.',
                'equipment_issue': 'false',
                'additional_task': 'false',
                'incident': 'false',
                'remarks': 'Busy evening shift.'
            }, follow_redirects=True)
            
            self.assertEqual(response.status_code, 200)
            
            # Check database insertion
            report = StaffPerformanceReport.query.filter_by(user_id=self.staff.id).first()
            self.assertIsNotNone(report)
            self.assertEqual(report.shift, 'Evening')
            self.assertEqual(report.tests_processed, 45)
            self.assertEqual(report.patients_booked, 10)
            self.assertTrue(report.qc_issue)
            self.assertEqual(report.qc_details, 'Instrument calibration error.')
            self.assertIn('Chemistry', report.section)
            self.assertIn('Hematology', report.section)

    def test_staff_profile_update(self):
        with self.app.test_client() as client:
            with client.session_transaction() as sess:
                sess['_user_id'] = str(self.staff.id)
                sess['_fresh'] = True
                
            response = client.post('/reports/staff/profile/update', data={
                'designation': 'Senior Technologist',
                'overall_experience': '5.5',
                'cdc_experience': '3.0',
                'qualification': 'MS/M.phil',
                'other_certificates': 'DIT Diploma',
                'sections': ['Chemistry', 'Molecular Biology'],
                'study_further': 'No',
                'research_interest': 'Yes',
                'training_requested': 'Advanced HPLC'
            }, follow_redirects=True)
            
            self.assertEqual(response.status_code, 200)
            
            # Verify DB updates
            profile = StaffProfile.query.filter_by(user_id=self.staff.id).first()
            self.assertEqual(profile.designation, 'Senior Technologist')
            self.assertEqual(profile.qualification, 'MS/M.phil')
            self.assertEqual(profile.overall_experience, 5.5)
            self.assertEqual(profile.study_further, 'No')
            self.assertEqual(profile.research_interest, 'Yes')

    def test_admin_staff_analytics_view_unauthorized(self):
        with self.app.test_client() as client:
            # 1. Test unauthorized access (role: LAB_STAFF)
            with client.session_transaction() as sess:
                sess['_user_id'] = str(self.staff.id)
                sess['_fresh'] = True
            response = client.get('/reports/staff/admin')
            self.assertEqual(response.status_code, 403) # Forbidden

    def test_admin_staff_analytics_view_authorized(self):
        with self.app.test_client() as client:
            # 2. Test authorized access (role: ADMIN)
            with client.session_transaction() as sess:
                sess['_user_id'] = str(self.admin.id)
                sess['_fresh'] = True
            response = client.get('/reports/staff/admin')
            self.assertEqual(response.status_code, 200)
            html = response.data.decode('utf-8')
            self.assertIn('Staff Performance', html)
            self.assertIn('Skills Analytics', html)
            self.assertIn('Lab Staff Member', html)

if __name__ == '__main__':
    unittest.main()
