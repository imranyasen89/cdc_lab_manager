"""Additive, idempotent schema upgrade run when the app starts.

The project has no migration step on Vercel, and db.create_all() never adds new
columns to tables that already exist. This compares the models with the live
database and only ADDS what is missing (tables, nullable columns, indexes). It
never drops or alters existing columns, so it is safe to run on every cold start.
"""
import logging

from sqlalchemy import inspect, text
from sqlalchemy.schema import CreateIndex

log = logging.getLogger(__name__)


def _existing_columns(conn):
    if conn.dialect.name == 'postgresql':
        rows = conn.execute(text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema()"))
    else:
        insp = inspect(conn)
        rows = [(t, c['name']) for t in insp.get_table_names() for c in insp.get_columns(t)]
    found = {}
    for table, column in rows:
        found.setdefault(table, set()).add(column)
    return found


def upgrade_schema(db):
    """Add missing tables/columns/indexes. Returns a list of changes made."""
    changes = []
    engine = db.engine
    with engine.begin() as conn:
        existing = _existing_columns(conn)
        if not existing:
            return changes  # empty database: `flask init-db` / create_all creates everything
        pg = conn.dialect.name == 'postgresql'
        for table in db.metadata.sorted_tables:
            if table.name not in existing:
                table.create(conn, checkfirst=True)
                changes.append(f"created table {table.name}")
                continue
            for column in table.columns:
                if column.name in existing[table.name]:
                    continue
                if not column.nullable and column.server_default is None:
                    log.warning("Not adding NOT NULL column %s.%s automatically", table.name, column.name)
                    continue
                col_type = column.type.compile(dialect=conn.dialect)
                if_not_exists = 'IF NOT EXISTS ' if pg else ''
                conn.execute(text(
                    f'ALTER TABLE "{table.name}" ADD COLUMN {if_not_exists}"{column.name}" {col_type}'))
                changes.append(f"added column {table.name}.{column.name}")
                for index in table.indexes:
                    if column.name in index.columns.keys():
                        stmt = str(CreateIndex(index).compile(dialect=conn.dialect))
                        conn.execute(text(stmt.replace('CREATE INDEX', 'CREATE INDEX IF NOT EXISTS', 1)))
                        changes.append(f"added index {index.name}")
    for change in changes:
        log.info("schema upgrade: %s", change)
    return changes
