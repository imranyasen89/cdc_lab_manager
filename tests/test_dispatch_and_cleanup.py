import os
import unittest

from app import create_app, db
from app.models import Branch, SampleRequest, User


class DispatchAndCleanupTestCase(unittest.TestCase):
    def setUp(self):
        self.old_db_url = os.environ.get('DATABASE_URL')
        os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()
        from seed import seed_data
        seed_data(self.app)
        self.client = self.app.test_client()
        self.client.post('/login', data={'username': 'branch11', 'password': 'branch11123'})

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()
        if self.old_db_url is not None:
            os.environ['DATABASE_URL'] = self.old_db_url
        else:
            os.environ.pop('DATABASE_URL', None)

    def test_multi_patient_dispatch_creates_batch(self):
        before = SampleRequest.query.count()
        resp = self.client.post('/branch/request/create', data={
            'handed_over_to': 'Ahmed Courier',
            'p-0-name': 'Ali', 'p-0-tests': 'CBC', 'p-0-qty-EDTA': '1', 'p-0-age': '30Y',
            'p-1-name': 'Sara', 'p-1-tests': 'PT/INR', 'p-1-qty-CITRATE': '2', 'p-1-condition': 'Hemolyzed',
            'p-2-name': '',  # empty row is ignored
        })
        self.assertEqual(resp.status_code, 302)
        new = SampleRequest.query.filter(SampleRequest.batch_id.isnot(None)).order_by(SampleRequest.id).all()
        self.assertEqual(SampleRequest.query.count(), before + 2)
        self.assertEqual(len({r.batch_id for r in new}), 1)
        self.assertEqual(new[1].samples[0].container, 'CITRATE')
        self.assertEqual(new[1].samples[0].quantity, 2)
        self.assertEqual(new[1].samples[0].condition, 'Hemolyzed')
        self.assertEqual(new[0].handed_over_to, 'Ahmed Courier')
        self.assertEqual(new[0].test_requested, 'CBC')

    def test_row_without_samples_is_rejected(self):
        before = SampleRequest.query.count()
        self.client.post('/branch/request/create', data={'p-0-name': 'Ali', 'p-0-tests': 'CBC'})
        self.assertEqual(SampleRequest.query.count(), before)

    def test_remove_demo_data_keeps_admin_and_riders_without_replacement(self):
        from app.services.demo_cleanup import remove_demo_data
        result = remove_demo_data()
        self.assertIn('tech', result['users'])
        self.assertEqual(result['kept_riders'], ['rider1', 'rider2', 'rider3'])
        self.assertIsNotNone(User.query.filter_by(username='admin').first())
        self.assertIsNone(User.query.filter_by(username='tech').first())
        self.assertIsNone(Branch.query.filter_by(code='G11').first())
        self.assertIsNotNone(Branch.query.filter_by(code='G8').first())


if __name__ == '__main__':
    unittest.main()
