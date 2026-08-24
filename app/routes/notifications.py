from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app import db
from app.models import Notification

notifications_bp = Blueprint('notifications', __name__)

@notifications_bp.route('/notifications')
@login_required
def list_notifications():
    # Fetch notifications belonging to current user or their role
    notifications_list = Notification.query.filter(
        (Notification.user_id == current_user.id) | (Notification.assigned_role == current_user.role)
    ).order_by(Notification.created_at.desc()).all()
    
    return render_template('notifications/list.html', notifications=notifications_list)

@notifications_bp.route('/notifications/mark-read/<int:notification_id>', methods=['POST'])
@login_required
def mark_read(notification_id):
    notif = Notification.query.get_or_404(notification_id)
    # Verify permission
    if notif.user_id == current_user.id or notif.assigned_role == current_user.role:
        notif.is_read = True
        db.session.commit()
        return jsonify({'status': 'success'})
    return jsonify({'status': 'error', 'message': 'Unauthorized'}), 403

@notifications_bp.route('/notifications/mark-all-read', methods=['POST'])
@login_required
def mark_all_read():
    notifs = Notification.query.filter(
        ((Notification.user_id == current_user.id) | (Notification.assigned_role == current_user.role)) &
        (Notification.is_read == False)
    ).all()
    for notif in notifs:
        notif.is_read = True
    db.session.commit()
    flash('All notifications marked as read.', 'success')
    return redirect(url_for('notifications.list_notifications'))

@notifications_bp.route('/notifications/unread-count')
@login_required
def unread_count():
    count = Notification.query.filter(
        ((Notification.user_id == current_user.id) | (Notification.assigned_role == current_user.role)) &
        (Notification.is_read == False)
    ).count()
    return jsonify({'count': count})
