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
        env = os.environ.get('FLASK_ENV', 'development')
        app.config.from_object(config.get(env, config['default']))
        
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
    
    # Import user model for login manager
    from app.models import User
    
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
        
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
