import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate

db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()

def create_app(config_class=None):
    app = Flask(__name__)
    
    # Configure app
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-12345')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///cdc_lab_manager.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    if config_class:
        app.config.from_object(config_class)
        
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
        
    return app
