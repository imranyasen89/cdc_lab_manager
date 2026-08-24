from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app import db
from app.models import User, Branch, Department, TATRule, OutsourcedLab, AuditLog
from app.utils.decorators import role_required
from app.utils.timezone import now_pkt

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/admin/users')
@login_required
@role_required('ADMIN')
def users():
    users_list = User.query.all()
    branches = Branch.query.all()
    departments = Department.query.all()
    return render_template('admin/users.html', users=users_list, branches=branches, departments=departments)

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
    user.role = request.form.get('role')
    branch_id = request.form.get('branch_id')
    department_id = request.form.get('department_id')
    user.branch_id = int(branch_id) if branch_id else None
    user.department_id = int(department_id) if department_id else None
    
    password = request.form.get('password')
    if password:
        user.set_password(password)
        
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
