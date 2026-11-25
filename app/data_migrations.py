"""Automatic one-time data steps run at start-up in production.

* Staff import: whenever app/data/cdc_staff.json changes (by content hash), the
  staff list is imported once. New accounts get the standard password
  (username + "123"); existing accounts keep their current password.
* Demo data removal: once real riders exist, the seed.py demo data is removed once.

Each step records a marker row in audit_logs so it never runs twice, and a
Postgres advisory lock stops parallel serverless instances from racing.
"""
import hashlib
import logging

from sqlalchemy import inspect, text

log = logging.getLogger(__name__)
LOCK_KEY = 726_351_001  # arbitrary constant for pg_advisory_xact_lock


def _staff_hash():
    from app.services.staff_import import DATA_FILE
    with open(DATA_FILE, 'rb') as fh:
        return hashlib.sha256(fh.read()).hexdigest()[:12]


def run_data_migrations(db):
    from app.models import AuditLog, User

    if not inspect(db.engine).has_table('audit_logs'):
        log.warning("data migration: skipped (empty database)")
        return []  # empty database
    done = []
    session = db.session
    try:
        if db.engine.dialect.name == 'postgresql':
            session.execute(text('SELECT pg_advisory_xact_lock(:k)'), {'k': LOCK_KEY})

        def marked(action):
            return session.query(AuditLog.id).filter(AuditLog.action == action).first() is not None

        staff_marker = f"AUTO_STAFF_IMPORT:{_staff_hash()}"
        if not marked(staff_marker):
            from app.services.staff_import import import_cdc_staff
            result = import_cdc_staff(reset_passwords=False)  # commits
            session.add(AuditLog(action=staff_marker,
                                 location=f"{result['created']} created, {result['updated']} updated"))
            session.commit()
            done.append(f"staff import: {result['created']} created, {result['updated']} updated, "
                        f"new branches: {', '.join(result['branches_created']) or 'none'}")
            if db.engine.dialect.name == 'postgresql':
                session.execute(text('SELECT pg_advisory_xact_lock(:k)'), {'k': LOCK_KEY})

        # One-time: staff first created by the old import_staff.py had passwords based on
        # their email-derived username; align everyone on the list to username + "123".
        reset_marker = "AUTO_STAFF_PASSWORD_RESET:v1"
        if not marked(reset_marker):
            from app.services.staff_import import import_cdc_staff
            from app.services.staff_import import remove_unused_duplicate_branches
            result = import_cdc_staff(reset_passwords=True)  # commits
            removed = remove_unused_duplicate_branches()
            session.add(AuditLog(action=reset_marker, location=f"{len(result['accounts'])} accounts"))
            session.commit()
            done.append(f"password reset to username+123 for {len(result['accounts'])} staff accounts; "
                        f"duplicate branches removed: {', '.join(removed) or 'none'}")
            if db.engine.dialect.name == 'postgresql':
                session.execute(text('SELECT pg_advisory_xact_lock(:k)'), {'k': LOCK_KEY})

        demo_marker = "AUTO_DEMO_CLEANUP:v1"
        real_riders = session.query(User.id).filter(User.role == 'RIDER', User.status.is_(True),
                                                    User.employee_id.notlike('EMP-200_')).count()
        if real_riders and not marked(demo_marker):
            from app.services.demo_cleanup import remove_demo_data
            result = remove_demo_data()  # commits
            session.add(AuditLog(action=demo_marker,
                                 location=f"{len(result['users'])} users, {result['requests']} requests"))
            session.commit()
            done.append(f"demo cleanup: removed {', '.join(result['users']) or 'no users'}; "
                        f"{result['requests']} requests; branches {', '.join(result['branches']) or 'none'}")
        session.commit()  # releases the advisory lock
    except Exception:
        session.rollback()
        raise
    finally:
        session.remove()
    for item in done or ['nothing to do']:
        log.warning("data migration: %s", item)
    return done
