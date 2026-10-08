import unittest
import os
from app import create_app, db
from app.models import (User, Branch, Department, TATRule, OutsourcedLab,
                        SampleType, SampleRequest, Sample, CenterDistance)

class MasterDataTestCase(unittest.TestCase):
    def setUp(self):
        self.old_db_url = os.environ.get('DATABASE_URL')
        os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
        
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()
        
        db.create_all()
        self.seed_admin_user()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()
        
        if self.old_db_url is not None:
            os.environ['DATABASE_URL'] = self.old_db_url
        else:
            os.environ.pop('DATABASE_URL', None)

    def seed_admin_user(self):
        self.admin = User(name="Admin User", username="admin", employee_id="A1", role="ADMIN", status=True)
        self.admin.set_password("admin123")
        db.session.add(self.admin)
        db.session.commit()

    def login_admin(self):
        return self.client.post('/login', data={
            'username': 'admin',
            'password': 'admin123'
        }, follow_redirects=True)

    def test_config_page_renders_with_all_sections(self):
        self.login_admin()
        res = self.client.get('/admin/config')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Master Data Control Console", res.data)
        self.assertIn(b"Branches", res.data)
        self.assertIn(b"Departments", res.data)
        self.assertIn(b"TAT Rules", res.data)
        self.assertIn(b"Outsourced Labs", res.data)
        self.assertIn(b"Specimen Types", res.data)

    def test_branch_crud(self):
        self.login_admin()

        # 1. Create Branch
        res = self.client.post('/admin/config/branch/create', data={
            'name': 'F-10 Collection Center',
            'code': 'F10',
            'latitude': '33.692',
            'longitude': '73.012',
            'address': 'F-10 Markaz, Islamabad'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        branch = Branch.query.filter_by(code='F10').first()
        self.assertIsNotNone(branch)
        self.assertEqual(branch.name, 'F-10 Collection Center')
        self.assertAlmostEqual(branch.latitude, 33.692)

        # 2. Reject duplicate code
        res_dup = self.client.post('/admin/config/branch/create', data={
            'name': 'Another F-10',
            'code': 'F10',
            'address': 'Duplicate'
        }, follow_redirects=True)
        self.assertIn(b"already exists", res_dup.data)

        # 3. Edit Branch
        res_edit = self.client.post(f'/admin/config/branch/edit/{branch.id}', data={
            'name': 'F-10 Main Hub',
            'code': 'F10-HUB',
            'latitude': '33.695',
            'longitude': '73.015',
            'address': 'Updated Address'
        }, follow_redirects=True)
        self.assertEqual(res_edit.status_code, 200)
        updated_branch = Branch.query.get(branch.id)
        self.assertEqual(updated_branch.name, 'F-10 Main Hub')
        self.assertEqual(updated_branch.code, 'F10-HUB')

        # 4. Safe Delete check with associated user
        staff_user = User(name="Staff", username="staff1", employee_id="S1", role="BRANCH_STAFF",
                          branch_id=branch.id, status=True)
        staff_user.set_password("pass")
        db.session.add(staff_user)
        db.session.commit()

        res_del_blocked = self.client.post(f'/admin/config/branch/delete/{branch.id}', follow_redirects=True)
        self.assertIn(b"Cannot delete branch", res_del_blocked.data)
        self.assertIsNotNone(Branch.query.get(branch.id))

        # Remove linked user, then delete branch
        db.session.delete(staff_user)
        db.session.commit()

        res_del = self.client.post(f'/admin/config/branch/delete/{branch.id}', follow_redirects=True)
        self.assertEqual(res_del.status_code, 200)
        self.assertIsNone(Branch.query.get(branch.id))

    def test_department_crud(self):
        self.login_admin()

        # 1. Create Department
        res = self.client.post('/admin/config/department/create', data={
            'name': 'Histopathology',
            'description': 'Tissue and biopsy pathology studies'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        dept = Department.query.filter_by(name='Histopathology').first()
        self.assertIsNotNone(dept)

        # 2. Duplicate Department
        res_dup = self.client.post('/admin/config/department/create', data={
            'name': 'Histopathology',
            'description': 'Duplicate'
        }, follow_redirects=True)
        self.assertIn(b"already exists", res_dup.data)

        # 3. Edit Department
        res_edit = self.client.post(f'/admin/config/department/edit/{dept.id}', data={
            'name': 'Histopathology & Cytology',
            'description': 'Biopsies, FNA, and Pap smears'
        }, follow_redirects=True)
        self.assertEqual(res_edit.status_code, 200)
        updated_dept = Department.query.get(dept.id)
        self.assertEqual(updated_dept.name, 'Histopathology & Cytology')

        # 4. Prevent delete when staff assigned
        tech = User(name="Pathologist", username="patho", employee_id="P1", role="LAB_STAFF",
                    department_id=dept.id, status=True)
        tech.set_password("pass")
        db.session.add(tech)
        db.session.commit()

        res_blocked = self.client.post(f'/admin/config/department/delete/{dept.id}', follow_redirects=True)
        self.assertIn(b"Cannot delete department", res_blocked.data)

        # Remove staff and delete
        db.session.delete(tech)
        db.session.commit()

        res_del = self.client.post(f'/admin/config/department/delete/{dept.id}', follow_redirects=True)
        self.assertIsNone(Department.query.get(dept.id))

    def test_outsourced_lab_crud(self):
        self.login_admin()

        # 1. Create Outsourced Lab
        res = self.client.post('/admin/config/outsourced-lab/create', data={
            'name': 'Chughtai Lab Partner',
            'contact_info': '051-2223334',
            'address': 'Blue Area, Islamabad'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        lab = OutsourcedLab.query.filter_by(name='Chughtai Lab Partner').first()
        self.assertIsNotNone(lab)

        # 2. Edit Outsourced Lab
        res_edit = self.client.post(f'/admin/config/outsourced-lab/edit/{lab.id}', data={
            'name': 'Chughtai Healthcare Lab',
            'contact_info': '051-9998887',
            'address': 'Jinnah Avenue, Islamabad'
        }, follow_redirects=True)
        self.assertEqual(res_edit.status_code, 200)
        updated_lab = OutsourcedLab.query.get(lab.id)
        self.assertEqual(updated_lab.name, 'Chughtai Healthcare Lab')
        self.assertEqual(updated_lab.contact_info, '051-9998887')

        # 3. Delete Outsourced Lab
        res_del = self.client.post(f'/admin/config/outsourced-lab/delete/{lab.id}', follow_redirects=True)
        self.assertEqual(res_del.status_code, 200)
        self.assertIsNone(OutsourcedLab.query.get(lab.id))

    def test_sample_type_crud(self):
        self.login_admin()

        # 1. Create Specimen Type
        res = self.client.post('/admin/config/sample-type/create', data={
            'name': 'Peritoneal Fluid',
            'code': 'PERIT',
            'description': 'Abdominal fluid aspiration'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        st = SampleType.query.filter_by(name='Peritoneal Fluid').first()
        self.assertIsNotNone(st)
        self.assertEqual(st.code, 'PERIT')

        # 2. Edit Specimen Type
        res_edit = self.client.post(f'/admin/config/sample-type/edit/{st.id}', data={
            'name': 'Peritoneal / Ascitic Fluid',
            'code': 'ASCIT',
            'description': 'Ascitic tap specimen'
        }, follow_redirects=True)
        self.assertEqual(res_edit.status_code, 200)
        updated_st = SampleType.query.get(st.id)
        self.assertEqual(updated_st.name, 'Peritoneal / Ascitic Fluid')
        self.assertEqual(updated_st.code, 'ASCIT')

        # 3. Delete Specimen Type
        res_del = self.client.post(f'/admin/config/sample-type/delete/{st.id}', follow_redirects=True)
        self.assertEqual(res_del.status_code, 200)
        self.assertIsNone(SampleType.query.filter_by(name='Peritoneal / Ascitic Fluid').first())

        # 4. Load standard specimen types
        res_seed = self.client.post('/admin/config/sample-type/seed-defaults', follow_redirects=True)
        self.assertEqual(res_seed.status_code, 200)
        self.assertGreater(SampleType.query.count(), 0)
        self.assertIsNotNone(SampleType.query.filter_by(name='Blood (EDTA)').first())

if __name__ == '__main__':
    unittest.main()
