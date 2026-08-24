import os
from app import create_app, db
from seed import seed_data

app = create_app()

if __name__ == '__main__':
    # Check if the database has already been seeded/created.
    # We will trigger the seeder to populate mock data on first execution.
    db_path = os.path.join(app.instance_path, 'cdc_lab_manager.db')
    if not os.path.exists(db_path):
        print("Database not found. Initializing and seeding demo data...")
        # Ensure instance directory exists
        os.makedirs(app.instance_path, exist_ok=True)
        seed_data()
        
    print("Starting Flask dev server...")
    app.run(debug=True, host='0.0.0.0', port=5000)
