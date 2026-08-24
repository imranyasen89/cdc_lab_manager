import unittest
from datetime import datetime, date
from app import create_app, db
from app.models import User, Branch, TATRule, SampleRequest, Sample, Task
from app.services.workflow_service import WorkflowService

class WorkflowTestCase(unittest.TestCase):
    def setUp(self):
        import os
        # Force SQLAlchemy to use isolated in-memory DB for tests
        self.old_db_url = os.environ.get('DATABASE_URL')
        os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
        
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.app_context = self.app.app_context()
        self.app_context.push()
        
        db.create_all()
        self.seed_test_data()

    def tearDown(self):
        import os
        db.session.remove()
        db.drop_all()
        self.app_context.pop()
        
        if self.old_db_url is not None:
            os.environ['DATABASE_URL'] = self.old_db_url
        else:
            os.environ.pop('DATABASE_URL', None)

    def seed_test_data(self):
        # Configure a test branch
        self.branch = Branch(name="Test G-11 Hub", code="T11", latitude=33.68, longitude=73.0)
        db.session.add(self.branch)
        
        # Configure TAT priority
        self.tat = TATRule(priority="Routine", max_tat_minutes=120, description="Test rule")
        db.session.add(self.tat)
        
        # Create users
        self.admin = User(name="Admin", username="admin", employee_id="E1", role="ADMIN", status=True)
        self.branch_staff = User(name="Branch Staff", username="bstaff", employee_id="E2", role="BRANCH_STAFF", status=True, branch=self.branch)
        self.rider = User(name="Ahmed Rider", username="rider", employee_id="E3", role="RIDER", status=True)
        self.lab_staff = User(name="Tech Staff", username="tech", employee_id="E4", role="LAB_STAFF", status=True)
        self.verifier = User(name="Dr Verifier", username="verifier", employee_id="E5", role="VERIFIER", status=True)
        
        for u in [self.admin, self.branch_staff, self.rider, self.lab_staff, self.verifier]:
            u.set_password("pass123")
            db.session.add(u)
            
        db.session.commit()

    def test_request_creation(self):
        # Create request
        req = SampleRequest(
            id="RIC-T11-20260820-000001",
            patient_name="Alice Smith",
            gender="Female",
            priority="Routine",
            branch_id=self.branch.id,
            created_by_id=self.branch_staff.id,
            status="Pickup Requested"
        )
        db.session.add(req)
        db.session.commit()
        
        self.assertEqual(req.status, "Pickup Requested")

    def test_invalid_transitions(self):
        req = SampleRequest(
            id="RIC-T11-20260820-000002",
            patient_name="Bob Brown",
            gender="Male",
            priority="Routine",
            branch_id=self.branch.id,
            created_by_id=self.branch_staff.id,
            status="Pickup Requested"
        )
        db.session.add(req)
        db.session.commit()
        
        # Test going directly to Sample Collected from Pickup Requested (should fail: needs Rider Assigned first)
        success, msg = WorkflowService.transition_to(
            request_id=req.id,
            new_status="Sample Collected",
            user=self.rider
        )
        self.assertFalse(success)
        self.assertIn("invalid", msg.lower())
        
        # Test going to Rider Assigned but without specifying a rider (should fail)
        success, msg = WorkflowService.transition_to(
            request_id=req.id,
            new_status="Rider Assigned",
            user=self.admin,
            extra_data={}
        )
        self.assertFalse(success)

    def test_role_guards(self):
        req = SampleRequest(
            id="RIC-T11-20260820-000003",
            patient_name="Charlie Cox",
            gender="Male",
            priority="Routine",
            branch_id=self.branch.id,
            created_by_id=self.branch_staff.id,
            status="Pickup Requested"
        )
        db.session.add(req)
        db.session.commit()
        
        # Branch staff trying to assign rider (should fail: only riders, supervisors, managers, admins can accept/assign)
        # Note: Role permissions map: 'Rider Assigned' -> ['RIDER', 'SUPERVISOR', 'MANAGER', 'ADMIN']
        success, msg = WorkflowService.transition_to(
            request_id=req.id,
            new_status="Rider Assigned",
            user=self.branch_staff,
            extra_data={'rider_id': self.rider.id}
        )
        self.assertFalse(success)
        self.assertIn("not authorized", msg.lower())

    def test_valid_workflow_path(self):
        req = SampleRequest(
            id="RIC-T11-20260820-000004",
            patient_name="Diana Prince",
            gender="Female",
            priority="Routine",
            branch_id=self.branch.id,
            created_by_id=self.branch_staff.id,
            status="Pickup Requested"
        )
        db.session.add(req)
        db.session.commit()
        
        # 1. Transition to Rider Assigned (Rider self-accepts)
        success, msg = WorkflowService.transition_to(
            request_id=req.id,
            new_status="Rider Assigned",
            user=self.rider,
            extra_data={'rider_id': self.rider.id, 'method': 'Self Assigned'}
        )
        self.assertTrue(success)
        self.assertEqual(req.status, "Rider Assigned")
        
        # 2. Transition to Sample Collected
        success, msg = WorkflowService.transition_to(
            request_id=req.id,
            new_status="Sample Collected",
            user=self.rider
        )
        self.assertTrue(success)
        self.assertEqual(req.status, "Sample Collected")
        
        # 3. Transition to Arrived at G-8
        success, msg = WorkflowService.transition_to(
            request_id=req.id,
            new_status="Arrived at G-8",
            user=self.rider
        )
        self.assertTrue(success)
        self.assertEqual(req.status, "Arrived at G-8")
        
        # 4. Transition to Received at G-8
        success, msg = WorkflowService.transition_to(
            request_id=req.id,
            new_status="Received at G-8",
            user=self.lab_staff
        )
        self.assertTrue(success)
        self.assertEqual(req.status, "Received at G-8")

    def test_create_request_route(self):
        # Log in the test client
        with self.app.test_client() as client:
            # Login session setup
            with client.session_transaction() as sess:
                sess['_user_id'] = str(self.branch_staff.id)
                sess['_fresh'] = True
            
            # Post create request
            response = client.post('/branch/request/create', data={
                'patient_name': 'Ayesha Khan',
                'gender': 'Female',
                'patient_id': 'MRN-999',
                'test_requested': 'CBC',
                'sample_type': 'Blood (EDTA)',
                'quantity': '1',
                'priority': 'Routine',
                'special_instructions': 'None'
            }, follow_redirects=True)
            
            self.assertEqual(response.status_code, 200)

if __name__ == '__main__':
    unittest.main()
