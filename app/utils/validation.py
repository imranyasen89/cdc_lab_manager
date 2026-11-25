"""Input validation safety net.

PostgreSQL (Supabase) enforces VARCHAR(n) limits, while SQLite (used by the
tests) silently accepts longer strings. Without a check, an over-long form value
only crashes in production with a 500. This module:

* validates String column lengths on every flush, raising a readable error;
* offers form_int / form_float helpers that reject non-numeric input;
* registers an error handler that rolls back, flashes the message and sends the
  user back to the page they came from instead of a 500.
"""
from flask import flash, redirect, request, url_for, jsonify
from sqlalchemy import String, event
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session


class InputError(ValueError):
    """User-supplied input is invalid; shown to the user as a flash message."""


def _label(column_name):
    return column_name.replace('_', ' ').capitalize()


def form_int(name, default=None, minimum=None):
    """Read an integer form field; raise InputError for non-numeric values."""
    raw = request.form.get(name)
    if raw is None or str(raw).strip() == '':
        if default is None:
            raise InputError(f"{_label(name)} is required.")
        return default
    try:
        value = int(str(raw).strip())
    except ValueError:
        raise InputError(f"{_label(name)} must be a whole number.")
    if minimum is not None and value < minimum:
        raise InputError(f"{_label(name)} must be at least {minimum}.")
    return value


def form_float(name, default=None, minimum=None):
    """Read a decimal form field; raise InputError for non-numeric values."""
    raw = request.form.get(name)
    if raw is None or str(raw).strip() == '':
        if default is None:
            raise InputError(f"{_label(name)} is required.")
        return default
    try:
        value = float(str(raw).strip())
    except ValueError:
        raise InputError(f"{_label(name)} must be a number.")
    if value != value or value in (float('inf'), float('-inf')):
        raise InputError(f"{_label(name)} must be a number.")
    if minimum is not None and value < minimum:
        raise InputError(f"{_label(name)} must be at least {minimum}.")
    return value


@event.listens_for(Session, 'before_flush')
def _check_string_lengths(session, flush_context, instances):
    for obj in list(session.new) + list(session.dirty):
        table = getattr(obj, '__table__', None)
        if table is None:
            continue
        for column in table.columns:
            if not isinstance(column.type, String) or not column.type.length:
                continue
            value = getattr(obj, column.key, None)
            if isinstance(value, str) and len(value) > column.type.length:
                raise InputError(
                    f"{_label(column.key)} is too long "
                    f"({len(value)} characters; maximum is {column.type.length})."
                )


def register_error_handlers(app):
    from app import db

    def _respond(message):
        db.session.rollback()
        if request.path.startswith('/api/') or request.accept_mimetypes.best == 'application/json':
            return jsonify(success=False, error=message), 400
        flash(message, 'danger')
        target = request.referrer
        if not target or not target.startswith(request.host_url):
            target = url_for('auth.index')
        return redirect(target)

    @app.errorhandler(InputError)
    def _handle_input_error(err):
        return _respond(str(err))

    @app.errorhandler(DataError)
    def _handle_data_error(err):
        app.logger.warning("DataError: %s", err)
        return _respond("Some of the values entered are invalid or too long. Please check the form and try again.")

    @app.errorhandler(IntegrityError)
    def _handle_integrity_error(err):
        app.logger.warning("IntegrityError: %s", err)
        return _respond("This record conflicts with existing data (for example a duplicate name or code).")


def to_int(value, name='value'):
    """Convert an already-read input value to int, or raise InputError."""
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        raise InputError(f"{_label(name)} must be a whole number.")


def to_float(value, name='value'):
    """Convert an already-read input value to float, or raise InputError."""
    try:
        result = float(str(value).strip())
    except (ValueError, TypeError):
        raise InputError(f"{_label(name)} must be a number.")
    if result != result or result in (float('inf'), float('-inf')):
        raise InputError(f"{_label(name)} must be a number.")
    return result
