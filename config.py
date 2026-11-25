import os

from sqlalchemy.pool import NullPool


def _database_url():
    """Return DATABASE_URL normalised to the psycopg (v3) driver.

    Supabase/Render/Railway/Vercel often provide postgres:// or postgresql://.
    Naming the driver explicitly (postgresql+psycopg://) keeps the driver the
    same whatever SQLAlchemy version is installed (2.0 defaults to psycopg2,
    2.1 to psycopg).
    """
    url = os.environ.get('DATABASE_URL', 'sqlite:///cdc_lab_manager.db')
    for prefix in ('postgres://', 'postgresql://', 'postgresql+psycopg2://'):
        if url.startswith(prefix):
            return 'postgresql+psycopg://' + url[len(prefix):]
    return url


def _engine_options(url):
    if url.startswith('sqlite'):
        return {}
    # Serverless (Vercel): every function instance is a separate process, so a
    # per-instance pool multiplies connections and quickly exhausts Supabase's
    # pooler ("max clients reached"). NullPool opens one connection per request
    # and closes it afterwards; the Supabase pooler does the pooling.
    # prepare_threshold=None disables server-side prepared statements, which
    # Supabase's transaction pooler (port 6543) does not support.
    return {
        'poolclass': NullPool,
        'connect_args': {
            'connect_timeout': 10,   # Fail fast if Supabase is unreachable
            'sslmode': os.environ.get('DATABASE_SSLMODE', 'require'),
            'prepare_threshold': None,
        },
    }


class Config:
    """Base configuration."""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-12345')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_DATABASE_URI = _database_url()
    SQLALCHEMY_ENGINE_OPTIONS = _engine_options(SQLALCHEMY_DATABASE_URI)


class DevelopmentConfig(Config):
    """Development configuration — uses SQLite unless DATABASE_URL is set."""
    DEBUG = True


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
