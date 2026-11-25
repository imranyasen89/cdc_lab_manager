"""Remove the demo data created by seed.py from a live database.

Removed: demo accounts (matched by BOTH seed username and seed employee ID, so a
real person who happens to share a username is never touched), the demo branches
G-10 / G-11 / G-13 and every request created by a demo account or at a demo branch,
together with their samples, tasks, history, notifications etc.

Kept: the `admin` account, G-8, imported staff and branches, and configuration
(TAT rules, departments, outsourced labs, sample types).

Demo riders are kept while no real (non-demo) active rider exists, so pickups
keep working; run again after adding real riders to remove them.
"""
from sqlalchemy import delete, select, update

from app import db
from app.models import Branch, SampleRequest, User

DEMO_USERS = {  # username: employee_id (from seed.py)
    'manager': 'EMP-1002', 'supervisor': 'EMP-1003', 'branch11': 'EMP-1004', 'tech': 'EMP-1005',
    'verifier': 'EMP-1006', 'ceo': 'EMP-1000',
    'rider1': 'EMP-2001', 'rider2': 'EMP-2002', 'rider3': 'EMP-2003',
}
DEMO_BRANCH_CODES = ['G10', 'G11', 'G13']
# Rows that belong to a person and go with them (rather than being re-assigned).
PER_USER_TABLES = {'user_task_permissions', 'staff_profiles', 'staff_performance_reports',
                   'location_records', 'notifications'}


def _fk_columns(target_table):
    """(table, column) pairs that reference target_table."""
    pairs = []
    for table in db.metadata.sorted_tables:
        for column in table.columns:
            for fk in column.foreign_keys:
                if fk.column.table.name == target_table:
                    pairs.append((table, column))
    return pairs


def find_demo_data():
    users = [u for u in User.query.filter(User.username.in_(DEMO_USERS)).all()
             if DEMO_USERS.get(u.username) == u.employee_id]
    real_riders = User.query.filter(User.role == 'RIDER', User.status.is_(True),
                                    User.id.notin_([u.id for u in users] or [0])).count()
    kept_riders = []
    if real_riders == 0:
        kept_riders = [u for u in users if u.role == 'RIDER']
        users = [u for u in users if u.role != 'RIDER']
    branches = Branch.query.filter(Branch.code.in_(DEMO_BRANCH_CODES)).all()
    user_ids = [u.id for u in users]
    branch_ids = [b.id for b in branches]
    requests = SampleRequest.query.filter(
        SampleRequest.created_by_id.in_(user_ids or [0]) | SampleRequest.branch_id.in_(branch_ids or [0])
    ).all()
    return {'users': users, 'branches': branches, 'requests': requests, 'kept_riders': kept_riders}


def remove_demo_data(dry_run=False):
    found = find_demo_data()
    summary = {
        'users': sorted(u.username for u in found['users']),
        'branches': sorted(b.name for b in found['branches']),
        'requests': len(found['requests']),
        'kept_riders': sorted(u.username for u in found['kept_riders']),
    }
    if dry_run:
        return summary

    admin = User.query.filter(User.role.in_(['SUPER_ADMIN', 'ADMIN']),
                              User.id.notin_([u.id for u in found['users']] or [0])).order_by(User.id).first()
    if admin is None:
        raise RuntimeError("No admin account would remain; aborting demo data removal.")

    request_ids = [r.id for r in found['requests']]
    user_ids = [u.id for u in found['users']]
    branch_ids = [b.id for b in found['branches']]
    session = db.session

    # 1. Requests and everything that hangs off them.
    if request_ids:
        for table, column in _fk_columns('sample_requests'):
            session.execute(delete(table).where(column.in_(request_ids)))
        session.execute(delete(SampleRequest.__table__).where(SampleRequest.id.in_(request_ids)))

    # 2. Demo users: per-person rows are deleted, other references point to the admin
    #    (or become empty where allowed) so real history is preserved.
    if user_ids:
        for table, column in _fk_columns('users'):
            where = column.in_(user_ids)
            if table.name in PER_USER_TABLES:
                session.execute(delete(table).where(where))
            elif column.nullable:
                session.execute(update(table).where(where).values({column.name: None}))
            else:
                session.execute(update(table).where(where).values({column.name: admin.id}))
        session.execute(delete(User.__table__).where(User.id.in_(user_ids)))

    # 3. Demo branches, only if nothing real still uses them.
    removed_branches = []
    for branch in found['branches']:
        in_use = session.execute(select(User.id).where(User.branch_id == branch.id).limit(1)).first() or \
                 session.execute(select(SampleRequest.id).where(SampleRequest.branch_id == branch.id).limit(1)).first()
        if in_use:
            continue
        for table, column in _fk_columns('branches'):
            if table.name in ('users', 'sample_requests'):
                continue
            if column.nullable:
                session.execute(update(table).where(column == branch.id).values({column.name: None}))
            else:
                session.execute(delete(table).where(column == branch.id))
        session.execute(delete(Branch.__table__).where(Branch.id == branch.id))
        removed_branches.append(branch.name)

    session.commit()
    summary['branches'] = sorted(removed_branches)
    return summary
