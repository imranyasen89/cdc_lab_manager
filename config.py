import os


class Config:
    """Base configuration."""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-12345')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Handle DATABASE_URL from Supabase/Render/Railway/Vercel etc.
    # They often provide postgres:// but SQLAlchemy 1.4+ requires postgresql://
    _db_url = os.environ.get('DATABASE_URL', 'sqlite:///cdc_lab_manager.db')
    if _db_url and _db_url.startswith('postgres://'):
        _db_url = _db_url.replace('postgres://', 'postgresql://', 1)
    SQLALCHEMY_DATABASE_URI = _db_url

    # Connection pool settings — critical for Supabase + serverless (Vercel)
    # Supabase limits concurrent connections; keep pool small and recycle often
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,       # Test connections before using them
        'pool_recycle': 300,         # Recycle connections every 5 minutes
        'pool_size': 5,              # Max persistent connections in pool
        'max_overflow': 2,           # Allow 2 extra connections under burst
        'connect_args': {
            'connect_timeout': 10,   # Fail fast if Supabase is unreachable
            'sslmode': 'require',    # Supabase requires SSL
        } if not _db_url.startswith('sqlite') else {}
    }


class DevelopmentConfig(Config):
    """Development configuration — uses SQLite unless DATABASE_URL is set."""
    DEBUG = True

    # Override pool settings for SQLite (SQLite doesn't support pool_size etc.)
    _dev_db = os.environ.get('DATABASE_URL', 'sqlite:///cdc_lab_manager.db')
    if _dev_db.startswith('sqlite'):
        SQLALCHEMY_ENGINE_OPTIONS = {}


class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False

    @classmethod
    def init_app(cls, app):
        # Log to stderr in production
        import logging
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(logging.INFO)
        app.logger.addHandler(stream_handler)


# Config dictionary for easy lookup
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
