import os

# Load environment variables from .env file (local development only)
# In production (Vercel/Render), env vars are set in the platform dashboard
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed — env vars must be set manually

from app import create_app

app = create_app()

if __name__ == '__main__':
    # Local development: auto-seed if SQLite DB is empty
    db_url = os.environ.get('DATABASE_URL', 'sqlite:///cdc_lab_manager.db')
    if db_url.startswith('sqlite'):
        db_path = os.path.join(app.instance_path, 'cdc_lab_manager.db')
        if not os.path.exists(db_path):
            print("SQLite database not found. Initializing and seeding demo data...")
            os.makedirs(app.instance_path, exist_ok=True)
            from seed import seed_data
            seed_data()

    print("Starting Flask dev server...")
    app.run(debug=True, host='0.0.0.0', port=5000)
