import os

# Load .env file early (for local development convenience)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate

db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()

def create_app(config_class=None):
    app = Flask(__name__)
    
    # Load configuration
    if config_class:
        app.config.from_object(config_class)
    else:
        from config import config
        env = (os.environ.get('FLASK_ENV') or 'development').strip().lower()
        # Vercel sets VERCEL_ENV=production on the live deployment.
        if os.environ.get('VERCEL_ENV') == 'production':
            env = 'production'
        app.config.from_object(config.get(env, config['default']))
        app.logger.info("Config: %s", env)
        
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    
    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'info'
    
    # Register Blueprints
    from app.routes.auth import auth_bp
    from app.routes.admin import admin_bp
    from app.routes.branch import branch_bp
    from app.routes.rider import rider_bp
    from app.routes.laboratory import lab_bp
    from app.routes.workflow import workflow_bp
    from app.routes.notifications import notifications_bp
    from app.routes.reports import reports_bp
    from app.routes.api import api_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(branch_bp)
    app.register_blueprint(rider_bp)
    app.register_blueprint(lab_bp)
    app.register_blueprint(workflow_bp)
    app.register_blueprint(notifications_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(api_bp)

    # Add any new tables/columns to an existing database (additive only).
    if app.config.get('AUTO_SCHEMA_UPGRADE', True) and not app.config['SQLALCHEMY_DATABASE_URI'].endswith(':memory:'):
        from app.schema_upgrade import upgrade_schema
        try:
            with app.app_context():
                upgrade_schema(db)
        except Exception:  # never block start-up; the error is logged
            app.logger.exception("Automatic schema upgrade failed")

    # One-time data steps (staff import, demo data removal) — production only.
    if app.config.get('AUTO_DATA_MIGRATIONS'):
        from app.data_migrations import run_data_migrations
        try:
            with app.app_context():
                run_data_migrations(db)
        except Exception:
            app.logger.exception("Automatic data migration failed")

    # Friendly handling of invalid / over-long input instead of HTTP 500
    from app.utils.validation import register_error_handlers
    register_error_handlers(app)
    
    # Import user model for login manager
    from app.models import User
    
    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))
        
    # Global context processor for notifications
    @app.context_processor
    def inject_notifications():
        from flask_login import current_user
        from app.models import Notification
        if current_user.is_authenticated:
            # Get notifications for user or user's role
            unread_count = Notification.query.filter(
                (Notification.user_id == current_user.id) | (Notification.assigned_role == current_user.role),
                Notification.is_read == False
            ).count()
            return dict(unread_notifications_count=unread_count)
        return dict(unread_notifications_count=0)

    # CLI commands
    import click

    @app.cli.command('init-db')
    def init_db_command():
        """Create any missing tables (safe to run repeatedly; never drops data)."""
        db.create_all()
        from app.schema_upgrade import upgrade_schema
        for change in upgrade_schema(db):
            click.echo(f"  {change}")
        click.echo('Database tables are up to date.')

    @app.cli.command('import-staff')
    @click.option('--keep-passwords', is_flag=True, help="Don't reset passwords of accounts that already exist.")
    def import_staff_command(keep_passwords):
        """Import CDC staff from app/data/cdc_staff.json (safe to re-run)."""
        from app.services.staff_import import import_cdc_staff
        result = import_cdc_staff(reset_passwords=not keep_passwords)
        for a in result['accounts']:
            click.echo(f"{a['username']:<22} {a['password']:<26} {a['role']:<13} {a['branch']}  ({a['name']})")
        click.echo(f"Created {result['created']}, updated {result['updated']} accounts; "
                   f"new branches: {', '.join(result['branches_created']) or 'none'}")

    @app.cli.command('remove-demo-data')
    @click.option('--dry-run', is_flag=True, help='Only list what would be removed.')
    def remove_demo_data_command(dry_run):
        """Delete seed.py demo accounts, branches and requests (keeps admin and real staff)."""
        from app.services.demo_cleanup import remove_demo_data
        result = remove_demo_data(dry_run=dry_run)
        click.echo(('Would remove: ' if dry_run else 'Removed: ') + str(result))

    @app.cli.command('seed')
    @click.option('--force', is_flag=True, help='Force re-seed even if data exists.')
    def seed_command(force):
        """Seed the database with demo data."""
        from app.models import User
        if User.query.first() and not force:
            click.echo('Database already contains data. Use --force to re-seed.')
            return
        from seed import seed_data
        seed_data()
        click.echo('Database seeded successfully!')
        
    return app
