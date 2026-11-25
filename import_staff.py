"""Import CDC staff into the database (same as `flask --app run import-staff`).

Data: app/data/cdc_staff.json (normalised from the cdc-staff sheet of CDC_lab.xlsx).
Usage:  python import_staff.py
"""
from app import create_app
from app.services.staff_import import import_cdc_staff

if __name__ == '__main__':
    app = create_app()
    with app.app_context():
        result = import_cdc_staff()
        for a in result['accounts']:
            print(f"{a['username']:<22} {a['password']:<26} {a['role']:<13} {a['branch']}  ({a['name']})")
        print(f"Created {result['created']}, updated {result['updated']}; "
              f"new branches: {', '.join(result['branches_created']) or 'none'}")
