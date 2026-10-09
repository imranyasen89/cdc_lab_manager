from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app import db
from app.models import SampleRequest, Sample, Task, StatusHistory, AuditLog, TATRule, Branch
from app.utils.decorators import role_required
from app.services.workflow_service import WorkflowService
from app.utils.timezone import now_pkt
from app.utils.date_filter import get_date_range

branch_bp = Blueprint('branch', __name__)

def generate_request_id(branch_code):
    """
    Generates a unique tracking ID: CDC-<BranchCode>-<YYYYMMDD>-<SeqNum>
    """
    code_clean = (branch_code or 'HQ').strip().replace(' ', '').upper()
    today_str = now_pkt().strftime('%Y%m%d')
    prefix = f"CDC-{code_clean}-{today_str}-"
    
    # Query all requests for this branch today
    requests = SampleRequest.query.filter(
        SampleRequest.id.like(f"{prefix}%")
    ).all()
    
    max_seq = 0
    for r in requests:
        try:
            # Suffix is the last part
            suffix = int(r.id.split('-')[-1])
            if suffix > max_seq:
                max_seq = suffix
        except (ValueError, IndexError):
            pass
            
    seq_num = str(max_seq + 1).zfill(6)
    return f"{prefix}{seq_num}"

@branch_bp.route('/branch/dashboard')
@login_required
@role_required('BRANCH_STAFF', 'ADMIN', 'MANAGER', 'SUPER_ADMIN')
def dashboard():
    preset = request.args.get('preset')
    start_date_param = request.args.get('start_date')
    end_date_param = request.args.get('end_date')
    
    start_dt, end_dt, start_date, end_date, active_preset, date_label = get_date_range(
        preset=preset,
        start_date_str=start_date_param,
        end_date_str=end_date_param,
        default_preset='all'
    )
    
    query = SampleRequest.query
    if current_user.role == 'BRANCH_STAFF':
        branch = current_user.branch
        if not branch:
            flash('Your user account is not associated with any branch. Please contact an Admin.', 'warning')
            return render_template('branch/dashboard.html', requests=[])
        query = query.filter_by(branch_id=branch.id)
    else:
        branch = None
        
    if start_dt and end_dt:
        query = query.filter(SampleRequest.created_at.between(start_dt, end_dt))
        
    requests_list = query.order_by(SampleRequest.created_at.desc()).all()
        
    return render_template('branch/dashboard.html',
                           requests=requests_list,
                           branch=branch,
                           active_preset=active_preset,
                           date_label=date_label,
                           start_date_str=start_date.strftime('%Y-%m-%d') if start_date else '',
                           end_date_str=end_date.strftime('%Y-%m-%d') if end_date else '')

@branch_bp.route('/branch/request/create', methods=['GET', 'POST'])
@login_required
@role_required('BRANCH_STAFF', 'ADMIN', 'MANAGER', 'SUPER_ADMIN')
def create_request():
    branches = Branch.query.all()
    user_branch = current_user.branch
    priorities = TATRule.query.all()
    
    if request.method == 'POST':
        if current_user.role in ['ADMIN', 'SUPER_ADMIN', 'MANAGER']:
            branch_id = request.form.get('branch_id')
            branch = Branch.query.get(branch_id) if branch_id else None
        else:
            branch = user_branch
            
        if not branch:
            flash('A valid branch must be selected to create a request.', 'danger')
            return redirect(url_for('branch.dashboard'))
            
        patient_name = request.form.get('patient_name')
        gender = request.form.get('gender')
        patient_id = request.form.get('patient_id')
        test_requested = request.form.get('test_requested')
        quantity = int(request.form.get('quantity', 1))
        priority = request.form.get('priority', 'Routine')
        special_instructions = request.form.get('special_instructions')
        
        # Collect selected sample types from checkboxes (supports both list and single value)
        selected_sample_types = request.form.getlist('sample_types')
        if not selected_sample_types and request.form.get('sample_type'):
            selected_sample_types = [request.form.get('sample_type')]
        other_type = request.form.get('other_sample_type', '').strip()
        
        # Replace 'Other' placeholder with custom text if provided
        if 'Other' in selected_sample_types and other_type:
            selected_sample_types = [t if t != 'Other' else other_type for t in selected_sample_types]
        elif 'Other' in selected_sample_types:
            selected_sample_types = [t for t in selected_sample_types if t != 'Other']
        
        if not selected_sample_types:
            flash('Please select at least one sample type.', 'danger')
            return render_template('branch/create_request.html', priorities=priorities, branches=branches, user_branch=user_branch)
        
        request_id = generate_request_id(branch.code)
        sample_types_str = ', '.join(selected_sample_types)
        
        # Create SampleRequest
        req = SampleRequest(
            id=request_id,
            patient_name=patient_name,
            gender=gender,
            patient_id=patient_id,
            priority=priority,
            branch=branch,
            created_by_id=current_user.id,
            special_instructions=special_instructions,
            status='Pickup Requested'
        )
        db.session.add(req)
        db.session.flush()
        
        # Create one Sample record per selected type
        for st in selected_sample_types:
            sample = Sample(
                request_id=request_id,
                sample_type=st,
                quantity=quantity
            )
            db.session.add(sample)
        
        # Log status history
        history = StatusHistory(
            request_id=request_id,
            status='Pickup Requested',
            changed_by_id=current_user.id,
            remarks=f"Request created with service: {test_requested}. Samples: {sample_types_str}",
            location=branch.name
        )
        db.session.add(history)
        
        # Log Audit
        audit = AuditLog(
            user_id=current_user.id,
            action="REQUEST_CREATE",
            request_id=request_id,
            old_status=None,
            new_status="Pickup Requested",
            location=branch.name,
            ip_address=request.remote_addr
        )
        db.session.add(audit)
        
        # Create initial Task for Riders
        task = Task(
            task_type='PICKUP',
            request_id=request_id,
            assigned_role='RIDER',
            status='PENDING',
            location=branch.name,
            remarks=f"Collect {quantity}x of: {sample_types_str}"
        )
        db.session.add(task)
        
        WorkflowService._send_notifications(req, None, 'Pickup Requested', current_user, None)
        
        db.session.commit()
        flash(f"Pickup request {request_id} created successfully.", 'success')
        return redirect(url_for('branch.dashboard'))
        
    return render_template('branch/create_request.html', priorities=priorities, branches=branches, user_branch=user_branch)

