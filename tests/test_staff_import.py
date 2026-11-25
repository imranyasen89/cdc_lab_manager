import os
import unittest

from app import create_app, db
from app.models import Branch, User
from app.services.staff_import import import_cdc_staff, load_staff
from app.services.workflow_service import WorkflowService
from app.utils.decorators import LAB_ROLES


class StaffImportTestCase(unittest.TestCase):
    def setUp(self):
        self.old_db_url = os.environ.get('DATABASE_URL')
        os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()
        if self.old_db_url is not None:
            os.environ['DATABASE_URL'] = self.old_db_url
        else:
            os.environ.pop('DATABASE_URL', None)

    def test_import_is_idempotent_and_assigns_roles(self):
        staff = load_staff()
        first = import_cdc_staff()
        second = import_cdc_staff()
        self.assertEqual(first['created'], len(staff))
        self.assertEqual(second['created'], 0)
        self.assertEqual(second['updated'], len(staff))
        self.assertEqual(User.query.count(), len(staff))

        g8 = Branch.query.filter_by(code='G8').first()
        for user in User.query.all():
            if user.role == 'RIDER':
                continue
            if user.branch_id == g8.id:
                self.assertIn(user.role, LAB_ROLES)
            else:
                self.assertEqual(user.role, 'BRANCH_STAFF')

        self.assertEqual(User.query.filter_by(role='RIDER').count(), 6)
        self.assertTrue(User.query.filter_by(username='m.yasir').first().check_password('m.yasir123'))
        user = User.query.filter_by(username='naveed.ullah').first()
        self.assertTrue(user.check_password('naveed.ullah123'))

    def test_all_lab_roles_can_do_every_in_lab_step(self):
        in_lab = ['Received at G-8', 'Processing', 'Processing Completed', 'Outsource Requested',
                  'Outsourced Result Received', 'Pending Verification', 'Verified',
                  'Correction Required', 'Completed', 'Rider Assigned']
        for status in in_lab:
            for role in LAB_ROLES:
                self.assertIn(role, WorkflowService.ROLE_PERMISSIONS[status], (status, role))
        # Branch staff and riders keep their limited steps.
        self.assertNotIn('BRANCH_STAFF', WorkflowService.ROLE_PERMISSIONS['Processing'])
        self.assertNotIn('LAB_STAFF', WorkflowService.ROLE_PERMISSIONS['Sample Collected'])


if __name__ == '__main__':
    unittest.main()
