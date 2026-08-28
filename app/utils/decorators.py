from functools import wraps
from flask import abort
from flask_login import current_user

def role_required(*roles):
    """
    Decorator to enforce Role-Based Access Control on routes.
    SUPER_ADMIN always passes any role check.
    Example: @role_required('ADMIN', 'MANAGER')
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401)
            # SUPER_ADMIN bypasses all role restrictions
            if current_user.role == 'SUPER_ADMIN':
                return f(*args, **kwargs)
            if current_user.role not in roles:
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator
