import unittest
from datetime import datetime, date, timedelta
import os
import json
import csv
import io
from app import create_app, db
from app.models import User, Branch, TATRule, SampleRequest, Sample, Task, LocationRecord
from app.routes.reports import get_performance_data

class ReportsTestCase(unittest.TestCase):
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
        # 1. Branch
        self.branch1 = Branch(name="G-11 Hub", code="G11", latitude=33.6822, longitude=73.0076)
        self.branch2 = Branch(name="G-10 Hub", code="G10", latitude=33.6896, longitude=73.0245)
        db.session.add_all([self.branch1, self.branch2])
        
        # 2. TAT Rule
        self.tat = TATRule(priority="Routine", max_tat_minutes=120, description="Routine")
        db.session.add(self.tat)
        
        # 3. Users
        self.admin = User(name="Admin User", username="admin", employee_id="EMP-1", role="ADMIN", status=True)
        self.branch_staff = User(name="Staff G11", username="staff11", employee_id="EMP-2", role="BRANCH_STAFF", status=True, branch=self.branch1)
        self.rider = User(name="Ahmed Rider", username="rider1", employee_id="EMP-3", role="RIDER", status=True)
        
        for u in [self.admin, self.branch_staff, self.rider]:
            u.set_password("pass123")
            db.session.add(u)
            
        db.session.commit()

        # 4. Sample Requests and Location Logs
        # Request 1 (today)
        self.req1 = SampleRequest(
            id="RIC-G11-20260822-000001",
            patient_name="John Doe",
            gender="Male",
            priority="Routine",
            branch_id=self.branch1.id,
            created_by_id=self.branch_staff.id,
            status="Sample Collected",
            created_at=datetime.utcnow()
        )
        db.session.add(self.req1)
        
        self.sample1 = Sample(request_id=self.req1.id, sample_type="Blood", quantity=3)
        self.sample2 = Sample(request_id=self.req1.id, sample_type="Urine", quantity=2)
        db.session.add_all([self.sample1, self.sample2])
        
        # Tasks for Request 1
        self.task1 = Task(
            task_type="PICKUP",
            request_id=self.req1.id,
            assigned_user_id=self.rider.id,
            status="COMPLETED",
            created_time=datetime.utcnow() - timedelta(minutes=30),
            completion_time=datetime.utcnow() - timedelta(minutes=15)
        )
        self.task2 = Task(
            task_type="TRANSPORT",
            request_id=self.req1.id,
            assigned_user_id=self.rider.id,
            status="IN_PROGRESS",
            created_time=datetime.utcnow() - timedelta(minutes=15)
        )
        db.session.add_all([self.task1, self.task2])
        
        # Location Records for rider today (Request 1)
        # Point 1: G-11 Hub coordinates
        self.loc1 = LocationRecord(
            request_id=self.req1.id,
            rider_id=self.rider.id,
            latitude=33.6822,
            longitude=73.0076,
            event_name="CONFIRM_COLLECTION",
            timestamp=datetime.utcnow() - timedelta(minutes=15)
        )
        # Point 2: G-10 Hub coordinates (about 1.76 km away)
        self.loc2 = LocationRecord(
            request_id=self.req1.id,
            rider_id=self.rider.id,
            latitude=33.6896,
            longitude=73.0245,
            event_name="PERIODIC_UPDATE",
            timestamp=datetime.utcnow() - timedelta(minutes=5)
        )
        db.session.add_all([self.loc1, self.loc2])
        
        db.session.commit()

    def test_get_performance_data_today(self):
        data = get_performance_data('today', None, None)
        
        self.assertEqual(data['preset'], 'today')
        
        # Verify branch stats
        branches = data['branches']
        g11_stats = next(b for b in branches if b['code'] == 'G11')
        self.assertEqual(g11_stats['generated'], 1)
        self.assertEqual(g11_stats['total_samples'], 5)  # 3 Blood + 2 Urine
        
        g10_stats = next(b for b in branches if b['code'] == 'G10')
        self.assertEqual(g10_stats['generated'], 0)
        self.assertEqual(g10_stats['total_samples'], 0)
        
        # Verify daily performance and distance covered
        daily = data['daily_performance']
        self.assertEqual(len(daily), 1)
        row = daily[0]
        self.assertEqual(row['emp_id'], 'EMP-3')
        self.assertEqual(row['handled'], 1)
        # G11 to G10 is about 1.76 km (Haversine formula calculation validation)
        self.assertGreater(row['distance'], 1.0)
        self.assertLess(row['distance'], 2.0)
        
        # Verify aggregate performance summary
        summaries = data['riders_summary']
        rider_sum = next(s for s in summaries if s['emp_id'] == 'EMP-3')
        self.assertEqual(rider_sum['handled'], 1)
        self.assertEqual(rider_sum['total_distance'], row['distance'])

    def test_performance_view_route(self):
        with self.app.test_client() as client:
            with client.session_transaction() as sess:
                sess['_user_id'] = str(self.admin.id)
                sess['_fresh'] = True
                
            response = client.get('/reports/performance?preset=weekly')
            self.assertEqual(response.status_code, 200)
            html = response.data.decode('utf-8')
            self.assertIn('Turnaround Time Performance', html)
            self.assertIn('Rider daily performance log', html)
            self.assertIn('5 samples', html)
            self.assertIn('1.77 km', html)

    def test_export_reports(self):
        with self.app.test_client() as client:
            with client.session_transaction() as sess:
                sess['_user_id'] = str(self.admin.id)
                sess['_fresh'] = True
                
            # Rider report export
            response = client.get('/reports/export/rider?preset=today')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.mimetype, 'text/csv')
            csv_content = response.data.decode('utf-8')
            reader = csv.reader(io.StringIO(csv_content))
            rows = list(reader)
            
            # Header check
            self.assertEqual(rows[0], ['Date', 'Rider Name', 'Employee ID', 'Tasks Handled', 'Distance Covered (km)', 'Avg Pickup Response (min)', 'Avg Transport Time (min)', 'TAT Violations'])
            # Data row check
            self.assertEqual(rows[1][1], 'Ahmed Rider')
            self.assertEqual(rows[1][2], 'EMP-3')
            self.assertEqual(rows[1][3], '1')
            self.assertEqual(rows[1][4], '1.77')

            # Branch report export
            response = client.get('/reports/export/branch?preset=today')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.mimetype, 'text/csv')
            csv_content = response.data.decode('utf-8')
            reader = csv.reader(io.StringIO(csv_content))
            rows = list(reader)
            
            # Header check
            self.assertEqual(rows[0], ['Branch Code', 'Branch Name', 'Total Requests Generated', 'Total Samples/Tests', 'Avg Pickup Time (min)', 'Avg Transport Time (min)', 'TAT Violations'])
            
            g11_row = next(r for r in rows if r[0] == 'G11')
            self.assertEqual(g11_row[2], '1') # Requests
            self.assertEqual(g11_row[3], '5') # Samples

if __name__ == '__main__':
    unittest.main()
