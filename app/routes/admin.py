from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app import db
from app.models import (User, Branch, Department, TATRule, OutsourcedLab, AuditLog,
                        SampleRequest, StatusHistory, Task, LocationRecord,
                        UserTaskPermission, CenterDistance, Sample)
from app.utils.decorators import role_required
from app.utils.timezone import now_pkt
from app.services.distance_service import DistanceService
from app.services.tat_service import TATService
from datetime import datetime, timedelta
from collections import defaultdict

admin_bp = Blueprint('admin', __name__)

TASK_PERMISSIONS = ['SAMPLE_RECEIVING', 'PROCESSING', 'RESULT_ENTRY', 'VERIFICATION', 'STAFF_WORKSPACE']

# ──────────────────── Admin Dashboard (KPI) ────────────────────

@admin_bp.route('/admin/dashboard')
@login_required
@role_required('ADMIN', 'MANAGER', 'SUPER_ADMIN')
def dashboard():
    today = now_pkt().date()
    start_dt = datetime.combine(today, datetime.min.time())
    end_dt = datetime.combine(today, datetime.max.time())
    
    # Today's requests
    today_requests = SampleRequest.query.filter(SampleRequest.created_at.between(start_dt, end_dt)).all()
    all_active = SampleRequest.query.filter(SampleRequest.status != 'Completed').all()
    
    # KPI stats
    total_today = len(today_requests)
    completed_today = sum(1 for r in today_requests if r.status == 'Completed')
    pending_today = sum(1 for r in today_requests if r.status != 'Completed')
    delayed_today = 0
    for r in today_requests:
        is_delayed, _, _ = TATService.check_is_delayed(r)
        if is_delayed:
            delayed_today += 1
    
    tat_compliance = round((1 - delayed_today / total_today) * 100, 1) if total_today > 0 else 100.0
    
    # Center workload
    branches = Branch.query.all()
    center_workload = []
    for b in branches:
        branch_requests = SampleRequest.query.filter_by(branch_id=b.id).all()
        active = [r for r in branch_requests if r.status != 'Completed']
        in_transit = sum(1 for r in active if r.status in ['Sample Collected', 'Rider Assigned'])
        processing = sum(1 for r in active if r.status in ['Received at G-8', 'Processing', 'Processing Completed'])
        completed = sum(1 for r in branch_requests if r.status == 'Completed')
        total_samples = sum(sum(s.quantity for s in r.samples) for r in branch_requests)
        center_workload.append({
            'branch': b,
            'active': len(active),
            'in_transit': in_transit,
            'processing': processing,
            'completed': completed,
            'total_samples': total_samples,
            'pending': sum(1 for r in active if r.status == 'Pickup Requested'),
        })
    
    # Rider performance summary (today)
    riders = User.query.filter_by(role='RIDER', status=True).all()
    rider_summaries = []
    for rider in riders:
        # Today's location records for distance
        locs = LocationRecord.query.filter(
            LocationRecord.rider_id == rider.id,
            LocationRecord.timestamp.between(start_dt, end_dt)
        ).order_by(LocationRecord.timestamp.asc()).all()
        
        distance = 0.0
        for i in range(len(locs) - 1):
            distance += DistanceService.calculate_distance(
                locs[i].latitude, locs[i].longitude,
                locs[i+1].latitude, locs[i+1].longitude
            )
        
        # Count samples carried today
        tasks_today = Task.query.filter(
            Task.assigned_user_id == rider.id,
            Task.task_type.in_(['PICKUP', 'TRANSPORT']),
            Task.created_time.between(start_dt, end_dt)
        ).all()
        samples_carried = 0
        handled_requests = set()
        for t in tasks_today:
            if t.request_id not in handled_requests:
                handled_requests.add(t.request_id)
                req = SampleRequest.query.get(t.request_id)
                if req:
                    samples_carried += sum(s.quantity for s in req.samples)
        
        active_tasks = Task.query.filter(
            Task.assigned_user_id == rider.id,
            Task.status.in_(['PENDING', 'IN_PROGRESS'])
        ).count()
        
        rider_summaries.append({
            'rider': rider,
            'distance': round(distance, 2),
            'samples_carried': samples_carried,
            'trips': len(handled_requests),
            'active_tasks': active_tasks,
        })
    
    # Center distances
    distances = CenterDistance.query.all()
    distance_map = {}
    for d in distances:
        distance_map[(d.from_branch_id, d.to_branch_id)] = d.distance_km
    
    return render_template('admin/dashboard.html',
        total_today=total_today,
        completed_today=completed_today,
        pending_today=pending_today,
        delayed_today=delayed_today,
        tat_compliance=tat_compliance,
        all_active_count=len(all_active),
        center_workload=center_workload,
        rider_summaries=rider_summaries,
        branches=branches,
        distance_map=distance_map,
        today=today.strftime('%Y-%m-%d')
    )

# ──────────────────── Users Management ────────────────────

@admin_bp.route('/admin/users')
@login_required
@role_required('ADMIN')
def users():
    users_list = User.query.all()
    branches = Branch.query.all()
    departments = Department.query.all()
    return render_template('admin/users.html', users=users_list, branches=branches, departments=departments, task_permissions=TASK_PERMISSIONS)

@admin_bp.route('/admin/users/create', methods=['POST'])
@login_required
@role_required('ADMIN')
def create_user():
    name = request.form.get('name')
    username = request.form.get('username')
    password = request.form.get('password')
    employee_id = request.form.get('employee_id')
    role = request.form.get('role')
    phone = request.form.get('phone')
    email = request.form.get('email')
    branch_id = request.form.get('branch_id')
    department_id = request.form.get('department_id')
    
    # Validation
    if User.query.filter_by(username=username).first():
        flash('Username already exists.', 'danger')
        return redirect(url_for('admin.users'))
    if User.query.filter_by(employee_id=employee_id).first():
        flash('Employee ID already registered.', 'danger')
        return redirect(url_for('admin.users'))
    
    # Prevent non-SUPER_ADMIN from creating SUPER_ADMIN accounts
    if role == 'SUPER_ADMIN' and current_user.role != 'SUPER_ADMIN':
        flash('Only Super Admin can create another Super Admin account.', 'danger')
        return redirect(url_for('admin.users'))
        
    user = User(
        name=name,
        username=username,
        employee_id=employee_id,
        role=role,
        phone=phone,
        email=email,
        branch_id=int(branch_id) if branch_id else None,
        department_id=int(department_id) if department_id else None,
        joining_date=now_pkt().date()
    )
    user.set_password(password)
    
    # Assign task permissions if provided
    selected_perms = request.form.getlist('task_permissions')
    for perm in selected_perms:
        if perm in TASK_PERMISSIONS:
            tp = UserTaskPermission(user=user, permission=perm)
            db.session.add(tp)
    
    db.session.add(user)
    db.session.commit()
    flash('User created successfully.', 'success')
    return redirect(url_for('admin.users'))

@admin_bp.route('/admin/users/edit/<int:user_id>', methods=['POST'])
@login_required
@role_required('ADMIN')
def edit_user(user_id):
    user = User.query.get_or_404(user_id)
    new_username = request.form.get('username')
    
    if new_username and new_username != user.username:
        # Check uniqueness
        duplicate = User.query.filter_by(username=new_username).first()
        if duplicate:
            flash('Username already exists on another account.', 'danger')
            return redirect(url_for('admin.users'))
        user.username = new_username

    user.name = request.form.get('name')
    user.phone = request.form.get('phone')
    user.email = request.form.get('email')
    
    new_role = request.form.get('role')
    # Prevent non-SUPER_ADMIN from assigning SUPER_ADMIN role
    if new_role == 'SUPER_ADMIN' and current_user.role != 'SUPER_ADMIN':
        flash('Only Super Admin can assign Super Admin role.', 'danger')
        return redirect(url_for('admin.users'))
    user.role = new_role
    
    branch_id = request.form.get('branch_id')
    department_id = request.form.get('department_id')
    user.branch_id = int(branch_id) if branch_id else None
    user.department_id = int(department_id) if department_id else None
    
    password = request.form.get('password')
    if password:
        user.set_password(password)
    
    # Update task permissions
    selected_perms = request.form.getlist('task_permissions')
    # Remove existing permissions
    UserTaskPermission.query.filter_by(user_id=user.id).delete()
    for perm in selected_perms:
        if perm in TASK_PERMISSIONS:
            tp = UserTaskPermission(user_id=user.id, permission=perm)
            db.session.add(tp)
        
    db.session.commit()
    flash('User updated successfully.', 'success')
    return redirect(url_for('admin.users'))

@admin_bp.route('/admin/users/toggle/<int:user_id>', methods=['POST'])
@login_required
@role_required('ADMIN')
def toggle_user(user_id):
    user = User.query.get_or_404(user_id)
    user.status = not user.status
    db.session.commit()
    status_str = "activated" if user.status else "deactivated"
    flash(f"User account {status_str} successfully.", 'success')
    return redirect(url_for('admin.users'))

@admin_bp.route('/admin/users/delete/<int:user_id>', methods=['POST'])
@login_required
@role_required('SUPER_ADMIN')
def delete_user(user_id):
    """Permanently delete a user account. Only SUPER_ADMIN can do this."""
    user = User.query.get_or_404(user_id)
    
    # Prevent self-deletion
    if user.id == current_user.id:
        flash('You cannot delete your own account.', 'danger')
        return redirect(url_for('admin.users'))
    
    # Prevent deleting other SUPER_ADMIN accounts
    if user.role == 'SUPER_ADMIN':
        flash('Cannot delete another Super Admin account.', 'danger')
        return redirect(url_for('admin.users'))
    
    user_name = user.name
    
    # Delete related task permissions
    UserTaskPermission.query.filter_by(user_id=user.id).delete()
    
    # Deactivate user and remove (soft delete by deactivation, then hard delete)
    db.session.delete(user)
    db.session.commit()
    
    flash(f'User "{user_name}" has been permanently deleted.', 'success')
    return redirect(url_for('admin.users'))

# ──────────────────── Task Permissions ────────────────────

@admin_bp.route('/admin/users/<int:user_id>/permissions', methods=['POST'])
@login_required
@role_required('ADMIN')
def update_permissions(user_id):
    user = User.query.get_or_404(user_id)
    selected_perms = request.form.getlist('permissions')
    
    # Clear existing
    UserTaskPermission.query.filter_by(user_id=user.id).delete()
    
    # Add new permissions
    for perm in selected_perms:
        if perm in TASK_PERMISSIONS:
            tp = UserTaskPermission(user_id=user.id, permission=perm)
            db.session.add(tp)
    
    db.session.commit()
    flash(f'Permissions updated for {user.name}.', 'success')
    return redirect(url_for('admin.users'))

# ──────────────────── Center Distances ────────────────────

@admin_bp.route('/admin/distances')
@login_required
@role_required('ADMIN', 'MANAGER')
def center_distances():
    branches = Branch.query.all()
    distances = CenterDistance.query.all()
    
    distance_map = {}
    for d in distances:
        distance_map[(d.from_branch_id, d.to_branch_id)] = {'km': d.distance_km, 'manual': d.is_manual}
    
    # Auto-calculate missing distances from GPS
    for b1 in branches:
        for b2 in branches:
            if b1.id != b2.id and (b1.id, b2.id) not in distance_map:
                if b1.latitude and b1.longitude and b2.latitude and b2.longitude:
                    auto_dist = DistanceService.calculate_distance(b1.latitude, b1.longitude, b2.latitude, b2.longitude)
                    distance_map[(b1.id, b2.id)] = {'km': auto_dist, 'manual': False}
    
    return render_template('admin/distances.html', branches=branches, distance_map=distance_map)

@admin_bp.route('/admin/distances/save', methods=['POST'])
@login_required
@role_required('ADMIN')
def save_distance():
    from_id = int(request.form.get('from_branch_id'))
    to_id = int(request.form.get('to_branch_id'))
    distance_km = float(request.form.get('distance_km'))
    
    # Save or update both directions
    for (fid, tid) in [(from_id, to_id), (to_id, from_id)]:
        existing = CenterDistance.query.filter_by(from_branch_id=fid, to_branch_id=tid).first()
        if existing:
            existing.distance_km = distance_km
            existing.is_manual = True
        else:
            cd = CenterDistance(from_branch_id=fid, to_branch_id=tid, distance_km=distance_km, is_manual=True)
            db.session.add(cd)
    
    db.session.commit()
    flash('Distance saved successfully.', 'success')
    return redirect(url_for('admin.center_distances'))

# ──────────────────── System Timeline ────────────────────

@admin_bp.route('/admin/timeline')
@login_required
@role_required('ADMIN', 'MANAGER', 'SUPERVISOR')
def timeline():
    # Date filters
    date_str = request.args.get('date', now_pkt().strftime('%Y-%m-%d'))
    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        target_date = now_pkt().date()
        date_str = target_date.strftime('%Y-%m-%d')
    
    start_dt = datetime.combine(target_date, datetime.min.time())
    end_dt = datetime.combine(target_date, datetime.max.time())
    
    # Get all status changes for the selected date
    history_entries = StatusHistory.query.filter(
        StatusHistory.timestamp.between(start_dt, end_dt)
    ).order_by(StatusHistory.timestamp.desc()).all()
    
    return render_template('admin/timeline.html', history=history_entries, date=date_str)

# ──────────────────── Configuration ────────────────────

@admin_bp.route('/admin/config')
@login_required
@role_required('ADMIN', 'MANAGER')
def config():
    branches = Branch.query.all()
    departments = Department.query.all()
    tat_rules = TATRule.query.all()
    outsourced_labs = OutsourcedLab.query.all()
    return render_template('admin/config.html', branches=branches, departments=departments, tat_rules=tat_rules, outsourced_labs=outsourced_labs)

@admin_bp.route('/admin/config/branch/create', methods=['POST'])
@login_required
@role_required('ADMIN')
def create_branch():
    name = request.form.get('name')
    code = request.form.get('code')
    address = request.form.get('address')
    lat = request.form.get('latitude')
    lng = request.form.get('longitude')
    
    if Branch.query.filter_by(code=code).first():
        flash('Branch code already exists.', 'danger')
        return redirect(url_for('admin.config'))
        
    branch = Branch(
        name=name,
        code=code,
        address=address,
        latitude=float(lat) if lat else None,
        longitude=float(lng) if lng else None
    )
    db.session.add(branch)
    db.session.commit()
    flash('Branch configured successfully.', 'success')
    return redirect(url_for('admin.config'))

@admin_bp.route('/admin/config/department/create', methods=['POST'])
@login_required
@role_required('ADMIN')
def create_department():
    name = request.form.get('name')
    desc = request.form.get('description')
    
    if Department.query.filter_by(name=name).first():
        flash('Department already exists.', 'danger')
        return redirect(url_for('admin.config'))
        
    dept = Department(name=name, description=desc)
    db.session.add(dept)
    db.session.commit()
    flash('Department created successfully.', 'success')
    return redirect(url_for('admin.config'))

@admin_bp.route('/admin/config/tat-rule/create', methods=['POST'])
@login_required
@role_required('ADMIN')
def create_tat_rule():
    priority = request.form.get('priority')
    max_tat = request.form.get('max_tat_minutes')
    desc = request.form.get('description')
    
    existing = TATRule.query.filter_by(priority=priority).first()
    if existing:
        existing.max_tat_minutes = int(max_tat)
        existing.description = desc
    else:
        rule = TATRule(priority=priority, max_tat_minutes=int(max_tat), description=desc)
        db.session.add(rule)
        
    db.session.commit()
    flash('TAT Rule configured successfully.', 'success')
    return redirect(url_for('admin.config'))

@admin_bp.route('/admin/config/tat-rule/edit/<int:rule_id>', methods=['POST'])
@login_required
@role_required('ADMIN')
def edit_tat_rule(rule_id):
    rule = TATRule.query.get_or_404(rule_id)
    priority = request.form.get('priority')
    max_tat = request.form.get('max_tat_minutes')
    desc = request.form.get('description')
    
    if priority != rule.priority:
        existing = TATRule.query.filter_by(priority=priority).first()
        if existing:
            flash(f"A TAT Rule with priority '{priority}' already exists.", 'danger')
            return redirect(url_for('admin.config'))
            
    rule.priority = priority
    rule.max_tat_minutes = int(max_tat)
    rule.description = desc
    db.session.commit()
    flash('TAT Rule updated successfully.', 'success')
    return redirect(url_for('admin.config'))

@admin_bp.route('/admin/config/tat-rule/delete/<int:rule_id>', methods=['POST'])
@login_required
@role_required('ADMIN')
def delete_tat_rule(rule_id):
    rule = TATRule.query.get_or_404(rule_id)
    rule_priority = rule.priority
    db.session.delete(rule)
    db.session.commit()
    flash(f"TAT Rule '{rule_priority}' deleted successfully.", 'success')
    return redirect(url_for('admin.config'))

@admin_bp.route('/admin/config/outsourced-lab/create', methods=['POST'])
@login_required
@role_required('ADMIN')
def create_outsourced_lab():
    name = request.form.get('name')
    contact = request.form.get('contact_info')
    address = request.form.get('address')
    
    lab = OutsourcedLab(name=name, contact_info=contact, address=address)
    db.session.add(lab)
    db.session.commit()
    flash('Outsourced Laboratory added successfully.', 'success')
    return redirect(url_for('admin.config'))

@admin_bp.route('/admin/audit-logs')
@login_required
@role_required('ADMIN', 'MANAGER')
def audit_logs():
    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(200).all()
    return render_template('admin/audit_logs.html', logs=logs)
