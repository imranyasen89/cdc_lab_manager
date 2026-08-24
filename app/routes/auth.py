from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from app import db
from app.models import User

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/')
def index():
    if current_user.is_authenticated:
        # Redirect to appropriate dashboard based on role
        if current_user.role == 'ADMIN':
            return redirect(url_for('admin.users'))
        elif current_user.role in ['MANAGER', 'SUPERVISOR']:
            return redirect(url_for('lab.dashboard'))
        elif current_user.role == 'BRANCH_STAFF':
            return redirect(url_for('branch.dashboard'))
        elif current_user.role == 'RIDER':
            return redirect(url_for('rider.dashboard'))
        elif current_user.role in ['LAB_STAFF', 'VERIFIER']:
            return redirect(url_for('lab.dashboard'))
    return redirect(url_for('auth.login'))

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('auth.index'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            if not user.status:
                flash('Your account has been deactivated. Please contact an Administrator.', 'danger')
                return render_template('auth/login.html')
                
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('auth.index'))
        else:
            flash('Invalid username or password.', 'danger')
            
    return render_template('auth/login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))

@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        current_user.name = request.form.get('name')
        current_user.phone = request.form.get('phone')
        current_user.email = request.form.get('email')
        
        new_password = request.form.get('password')
        if new_password:
            current_user.set_password(new_password)
            
        db.session.commit()
        flash('Profile updated successfully.', 'success')
        return redirect(url_for('auth.profile'))
        
    return render_template('auth/profile.html')
