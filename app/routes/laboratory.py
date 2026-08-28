from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app import db
from app.models import SampleRequest, User, Branch, OutsourcedLab, Sample, Task, TATRule, StatusHistory, AuditLog
from app.utils.decorators import role_required
from app.services.workflow_service import WorkflowService
from app.utils.timezone import now_pkt

lab_bp = Blueprint('lab', __name__)

@lab_bp.route('/lab/dashboard')
@login_required
@role_required('LAB_STAFF', 'VERIFIER', 'SUPERVISOR', 'MANAGER', 'ADMIN')
def dashboard():
    # Fetch lists for dashboards based on status
    unassigned = SampleRequest.query.filter_by(status='Pickup Requested').all()
    in_transit = SampleRequest.query.filter_by(status='Sample Collected').all()
    arrived = SampleRequest.query.filter_by(status='Arrived at G-8').all()
    
    received = SampleRequest.query.filter(SampleRequest.status.in_(['Received at G-8', 'Processing'])).all()
    
    processing_completed = SampleRequest.query.filter(
        SampleRequest.status.in_(['Processing Completed', 'Outsourced Result Received', 'Correction Required'])
    ).all()
    
    pending_verification = SampleRequest.query.filter_by(status='Pending Verification').all()
    verified = SampleRequest.query.filter_by(status='Verified').all()
    
    outsource_pending = SampleRequest.query.filter_by(status='Outsource Requested').all()
    outsource_sent = SampleRequest.query.filter_by(status='Sent to Outsourced Lab').all()
    
    # Active riders list for supervisor assignment
    riders = User.query.filter_by(role='RIDER', status=True).all()
    
    # Outsourced labs list
    outsource_labs = OutsourcedLab.query.all()
    
    return render_template(
        'laboratory/dashboard.html',
        unassigned=unassigned,
        in_transit=in_transit,
        arrived=arrived,
        received=received,
        processing_completed=processing_completed,
        pending_verification=pending_verification,
        verified=verified,
        outsource_pending=outsource_pending,
        outsource_sent=outsource_sent,
        riders=riders,
        outsource_labs=outsource_labs
    )

@lab_bp.route('/lab/assign-rider', methods=['POST'])
@login_required
@role_required('SUPERVISOR', 'MANAGER', 'ADMIN')
def assign_rider():
    request_id = request.form.get('request_id')
    rider_id = int(request.form.get('rider_id'))
    
    success, msg = WorkflowService.transition_to(
        request_id=request_id,
        new_status='Rider Assigned',
        user=current_user,
        remarks=f"Assigned to Rider ID: {rider_id}",
        location="G-8 Main Lab Supervisor Desk",
        ip_address=request.remote_addr,
        extra_data={'rider_id': rider_id, 'method': 'Lab Assigned'}
    )
    
    if success:
        flash('Rider assigned successfully.', 'success')
    else:
        flash(f"Error: {msg}", 'danger')
        
    return redirect(url_for('lab.dashboard'))

@lab_bp.route('/lab/receive/<request_id>', methods=['POST'])
@login_required
@role_required('LAB_STAFF', 'SUPERVISOR', 'MANAGER', 'ADMIN')
def receive_sample(request_id):
    action = request.form.get('action', 'accept')  # accept or reject
    condition = request.form.get('condition', 'Good')
    quantity = int(request.form.get('quantity', 1))
    remarks = request.form.get('remarks', '')
    
    if action == 'reject':
        # Reject means cancel request status, but for simplicity let's transition to a cancelled or separate state
        # Let's set it as Received with rejection remarks or cancel the request.
        # Section 7 says: "Acceptance/rejection, rejection reason if applicable, remarks. Status: Received at G-8"
        # We can record the rejection reason and mark as Received but flagged, or transition to a Rejected state.
        # Let's log it in StatusHistory and set status to Received at G-8 with rejection flag.
        status_remarks = f"REJECTED! Reason: {remarks}. Condition: {condition}."
    else:
        status_remarks = f"Accepted. Condition: {condition}. Qty: {quantity}. Remarks: {remarks}"
        
    success, msg = WorkflowService.transition_to(
        request_id=request_id,
        new_status='Received at G-8',
        user=current_user,
        remarks=status_remarks,
        location="G-8 Main Lab Receiving",
        ip_address=request.remote_addr
    )
    
    if success:
        flash('Sample receipt acknowledged.', 'success')
    else:
        flash(f"Error: {msg}", 'danger')
        
    return redirect(url_for('lab.dashboard'))

@lab_bp.route('/lab/process/start/<request_id>', methods=['POST'])
@login_required
@role_required('LAB_STAFF', 'ADMIN')
def start_processing(request_id):
    success, msg = WorkflowService.transition_to(
        request_id=request_id,
        new_status='Processing',
        user=current_user,
        remarks="Processing started in department.",
        location="G-8 Main Lab Processing Bench",
        ip_address=request.remote_addr
    )
    
    if success:
        flash('Processing started.', 'success')
    else:
        flash(f"Error: {msg}", 'danger')
        
    return redirect(url_for('lab.dashboard'))

@lab_bp.route('/lab/process/complete/<request_id>', methods=['POST'])
@login_required
@role_required('LAB_STAFF', 'ADMIN')
def complete_processing(request_id):
    remarks = request.form.get('remarks', '')
    success, msg = WorkflowService.transition_to(
        request_id=request_id,
        new_status='Processing Completed',
        user=current_user,
        remarks=f"Processing completed. {remarks}",
        location="G-8 Main Lab Processing Bench",
        ip_address=request.remote_addr
    )
    
    if success:
        flash('Processing completed successfully.', 'success')
    else:
        flash(f"Error: {msg}", 'danger')
        
    return redirect(url_for('lab.dashboard'))

@lab_bp.route('/lab/outsource/request/<request_id>', methods=['POST'])
@login_required
@role_required('LAB_STAFF', 'SUPERVISOR', 'MANAGER', 'ADMIN')
def request_outsource(request_id):
    outsourced_lab_id = int(request.form.get('outsourced_lab_id'))
    reason = request.form.get('reason', '')
    
    lab = OutsourcedLab.query.get(outsourced_lab_id)
    lab_name = lab.name if lab else "Outsourced Lab"
    
    success, msg = WorkflowService.transition_to(
        request_id=request_id,
        new_status='Outsource Requested',
        user=current_user,
        remarks=f"Outsource requested for {lab_name}. Reason: {reason}",
        location="G-8 Main Lab",
        ip_address=request.remote_addr,
        extra_data={'outsourced_lab': lab_name}
    )
    
    if success:
        flash('Sample marked for outsourcing.', 'success')
    else:
        flash(f"Error: {msg}", 'danger')
        
    return redirect(url_for('lab.dashboard'))

@lab_bp.route('/lab/outsource/send/<request_id>', methods=['POST'])
@login_required
@role_required('RIDER', 'LAB_STAFF', 'SUPERVISOR', 'MANAGER', 'ADMIN')
def send_outsource(request_id):
    remarks = request.form.get('remarks', 'Dispatched to outsourced lab.')
    success, msg = WorkflowService.transition_to(
        request_id=request_id,
        new_status='Sent to Outsourced Lab',
        user=current_user,
        remarks=remarks,
        location="G-8 Main Lab Dispatch Desk",
        ip_address=request.remote_addr
    )
    
    if success:
        flash('Sample dispatched to outsourced laboratory.', 'success')
    else:
        flash(f"Error: {msg}", 'danger')
        
    return redirect(url_for('lab.dashboard'))

@lab_bp.route('/lab/outsource/receive/<request_id>', methods=['POST'])
@login_required
@role_required('LAB_STAFF', 'SUPERVISOR', 'MANAGER', 'ADMIN')
def receive_outsource_result(request_id):
    remarks = request.form.get('remarks', 'Outsourced report received.')
    success, msg = WorkflowService.transition_to(
        request_id=request_id,
        new_status='Outsourced Result Received',
        user=current_user,
        remarks=remarks,
        location="G-8 Main Lab Receiving",
        ip_address=request.remote_addr
    )
    
    if success:
        flash('Outsourced results received.', 'success')
    else:
        flash(f"Error: {msg}", 'danger')
        
    return redirect(url_for('lab.dashboard'))

@lab_bp.route('/lab/result/enter/<request_id>', methods=['POST'])
@login_required
@role_required('LAB_STAFF', 'ADMIN')
def enter_result(request_id):
    ref_num = request.form.get('ref_num', '')
    remarks = request.form.get('remarks', '')
    
    success, msg = WorkflowService.transition_to(
        request_id=request_id,
        new_status='Pending Verification',
        user=current_user,
        remarks=f"Result/Report entered. HIMS Ref: {ref_num}. Remarks: {remarks}",
        location="G-8 Main Lab HIMS Desk",
        ip_address=request.remote_addr
    )
    
    if success:
        flash('Results entered and forwarded to Verifier.', 'success')
    else:
        flash(f"Error: {msg}", 'danger')
        
    return redirect(url_for('lab.dashboard'))

@lab_bp.route('/lab/verify/<request_id>', methods=['POST'])
@login_required
@role_required('VERIFIER', 'SUPERVISOR', 'MANAGER', 'ADMIN')
def verify_report(request_id):
    action = request.form.get('action', 'approve')  # approve or reject
    remarks = request.form.get('remarks', '')
    
    if action == 'approve':
        new_status = 'Verified'
        remarks_str = f"Report approved. Remarks: {remarks}"
    else:
        new_status = 'Correction Required'
        remarks_str = f"REJECTED. Correction Required: {remarks}"
        
    success, msg = WorkflowService.transition_to(
        request_id=request_id,
        new_status=new_status,
        user=current_user,
        remarks=remarks_str,
        location="G-8 Main Lab Verification Desk",
        ip_address=request.remote_addr
    )
    
    if success:
        if action == 'approve':
            flash('Report verified and approved.', 'success')
        else:
            flash('Report rejected and returned for correction.', 'warning')
    else:
        flash(f"Error: {msg}", 'danger')
        
    return redirect(url_for('lab.dashboard'))

@lab_bp.route('/lab/deliver/<request_id>', methods=['POST'])
@login_required
@role_required('BRANCH_STAFF', 'LAB_STAFF', 'RECEPTION_STAFF', 'SUPERVISOR', 'MANAGER', 'ADMIN')
def deliver_report(request_id):
    method = request.form.get('method', 'Branch Delivery')
    recipient = request.form.get('recipient', '')
    remarks = request.form.get('remarks', '')
    
    success, msg = WorkflowService.transition_to(
        request_id=request_id,
        new_status='Completed',
        user=current_user,
        remarks=f"Delivered via {method} to {recipient}. Remarks: {remarks}",
        location=f"Delivery Point ({method})",
        ip_address=request.remote_addr
    )
    
    if success:
        flash('Report delivery completed. Request is closed.', 'success')
    else:
        flash(f"Error: {msg}", 'danger')
        
    return redirect(url_for('lab.dashboard'))

# ──────────────────── Local Point Sample Input ────────────────────

def generate_local_request_id():
    """Generates a unique tracking ID for local samples: CDC-LOCAL-YYYYMMDD-SeqNum"""
    today_str = now_pkt().strftime('%Y%m%d')
    prefix = f"CDC-LOCAL-{today_str}-"
    
    requests = SampleRequest.query.filter(
        SampleRequest.id.like(f"{prefix}%")
    ).all()
    
    max_seq = 0
    for r in requests:
        try:
            suffix = int(r.id.split('-')[-1])
            if suffix > max_seq:
                max_seq = suffix
        except (ValueError, IndexError):
            pass
            
    seq_num = str(max_seq + 1).zfill(6)
    return f"{prefix}{seq_num}"

@lab_bp.route('/lab/local-receive', methods=['GET', 'POST'])
@login_required
@role_required('LAB_STAFF', 'SUPERVISOR', 'MANAGER', 'ADMIN')
def local_receive():
    """Accept samples directly at local center (walk-in), bypassing rider pickup flow."""
    priorities = TATRule.query.all()
    branches = Branch.query.all()
    
    if request.method == 'POST':
        patient_name = request.form.get('patient_name')
        gender = request.form.get('gender')
        patient_id = request.form.get('patient_id')
        priority = request.form.get('priority', 'Routine')
        special_instructions = request.form.get('special_instructions')
        receiving_branch_id = request.form.get('receiving_branch_id')
        quantity = int(request.form.get('quantity', 1))
        
        # Collect sample types
        selected_sample_types = request.form.getlist('sample_types')
        other_type = request.form.get('other_sample_type', '').strip()
        if 'Other' in selected_sample_types and other_type:
            selected_sample_types = [t if t != 'Other' else other_type for t in selected_sample_types]
        elif 'Other' in selected_sample_types:
            selected_sample_types = [t for t in selected_sample_types if t != 'Other']
        
        if not selected_sample_types:
            flash('Please select at least one sample type.', 'danger')
            return render_template('laboratory/local_receive.html', priorities=priorities, branches=branches)
        
        request_id = generate_local_request_id()
        sample_types_str = ', '.join(selected_sample_types)
        
        # Determine branch — default to first branch (G-8 HQ) if not specified
        branch_id = int(receiving_branch_id) if receiving_branch_id else (branches[0].id if branches else None)
        
        # Create SampleRequest — starts directly at 'Received at G-8' status
        req = SampleRequest(
            id=request_id,
            patient_name=patient_name,
            gender=gender,
            patient_id=patient_id,
            priority=priority,
            branch_id=branch_id,
            created_by_id=current_user.id,
            special_instructions=special_instructions,
            status='Received at G-8'
        )
        db.session.add(req)
        
        # Create sample records
        for st in selected_sample_types:
            sample = Sample(
                request_id=request_id,
                sample_type=st,
                quantity=quantity
            )
            db.session.add(sample)
        
        # Log status history - creation directly at Received
        history = StatusHistory(
            request_id=request_id,
            status='Received at G-8',
            changed_by_id=current_user.id,
            remarks=f"LOCAL POINT ENTRY: Walk-in sample received directly. Samples: {sample_types_str}",
            location="Local Center / Walk-in"
        )
        db.session.add(history)
        
        # Audit log
        audit = AuditLog(
            user_id=current_user.id,
            action="LOCAL_RECEIVE_CREATE",
            request_id=request_id,
            old_status=None,
            new_status="Received at G-8",
            location="Local Center / Walk-in",
            ip_address=request.remote_addr
        )
        db.session.add(audit)
        
        # Create process task immediately
        task = Task(
            task_type='PROCESS',
            request_id=request_id,
            assigned_role='LAB_STAFF',
            created_time=now_pkt(),
            status='PENDING',
            location="G-8 Main Lab",
            remarks=f"Local walk-in sample: {sample_types_str}"
        )
        db.session.add(task)
        
        db.session.commit()
        flash(f'Local sample {request_id} registered and ready for processing.', 'success')
        return redirect(url_for('lab.dashboard'))
    
    return render_template('laboratory/local_receive.html', priorities=priorities, branches=branches)

