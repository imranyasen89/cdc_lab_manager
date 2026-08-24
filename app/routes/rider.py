from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app import db
from app.models import SampleRequest, Task, LocationRecord
from app.utils.decorators import role_required
from app.services.workflow_service import WorkflowService
from datetime import datetime

rider_bp = Blueprint('rider', __name__)

@rider_bp.route('/rider/dashboard')
@login_required
@role_required('RIDER', 'ADMIN', 'SUPERVISOR')
def dashboard():
    # 1. Get rider's active tasks
    my_tasks = Task.query.filter(
        Task.assigned_user_id == current_user.id,
        Task.status.in_(['PENDING', 'IN_PROGRESS'])
    ).all()
    
    # 2. Get unassigned pickup requests (status: 'Pickup Requested')
    available_pickups = SampleRequest.query.filter_by(status='Pickup Requested').all()
    
    return render_template('rider/dashboard.html', my_tasks=my_tasks, available_pickups=available_pickups)

@rider_bp.route('/rider/task/<request_id>/accept', methods=['POST'])
@login_required
@role_required('RIDER', 'ADMIN', 'SUPERVISOR')
def accept_task(request_id):
    lat = request.form.get('latitude')
    lng = request.form.get('longitude')
    lat = float(lat) if lat else None
    lng = float(lng) if lng else None
    
    location_str = f"GPS: {lat}, {lng}" if (lat and lng) else "GPS: Denied/Unavailable"
    
    # Call workflow transition
    success, msg = WorkflowService.transition_to(
        request_id=request_id,
        new_status='Rider Assigned',
        user=current_user,
        remarks="Rider accepted pickup.",
        location=location_str,
        ip_address=request.remote_addr,
        extra_data={'rider_id': current_user.id, 'method': 'Self Assigned'}
    )
    
    if success:
        # Record location record if available
        if lat and lng:
            loc = LocationRecord(
                request_id=request_id,
                rider_id=current_user.id,
                latitude=lat,
                longitude=lng,
                event_name='ACCEPT_PICKUP'
            )
            db.session.add(loc)
            db.session.commit()
        flash('Pickup request accepted successfully.', 'success')
    else:
        flash(f"Error accepting task: {msg}", 'danger')
        
    return redirect(url_for('rider.dashboard'))

@rider_bp.route('/rider/task/<request_id>/collect', methods=['POST'])
@login_required
@role_required('RIDER', 'ADMIN')
def collect_sample(request_id):
    lat = request.form.get('latitude')
    lng = request.form.get('longitude')
    lat = float(lat) if lat else None
    lng = float(lng) if lng else None
    
    location_str = f"GPS: {lat}, {lng}" if (lat and lng) else "GPS: Unavailable"
    remarks = request.form.get('remarks', 'Collected samples.')
    
    success, msg = WorkflowService.transition_to(
        request_id=request_id,
        new_status='Sample Collected',
        user=current_user,
        remarks=remarks,
        location=location_str,
        ip_address=request.remote_addr
    )
    
    if success:
        if lat and lng:
            loc = LocationRecord(
                request_id=request_id,
                rider_id=current_user.id,
                latitude=lat,
                longitude=lng,
                event_name='CONFIRM_COLLECTION'
            )
            db.session.add(loc)
            db.session.commit()
        flash('Samples marked as Collected. In transit to G-8.', 'success')
    else:
        flash(f"Error: {msg}", 'danger')
        
    return redirect(url_for('rider.dashboard'))

@rider_bp.route('/rider/task/<request_id>/deliver', methods=['POST'])
@login_required
@role_required('RIDER', 'ADMIN')
def deliver_sample(request_id):
    lat = request.form.get('latitude')
    lng = request.form.get('longitude')
    lat = float(lat) if lat else None
    lng = float(lng) if lng else None
    
    location_str = f"GPS: {lat}, {lng}" if (lat and lng) else "GPS: G-8 Lab Gate"
    
    success, msg = WorkflowService.transition_to(
        request_id=request_id,
        new_status='Arrived at G-8',
        user=current_user,
        remarks="Samples delivered to G-8 entrance.",
        location=location_str,
        ip_address=request.remote_addr
    )
    
    if success:
        if lat and lng:
            loc = LocationRecord(
                request_id=request_id,
                rider_id=current_user.id,
                latitude=lat,
                longitude=lng,
                event_name='ARRIVE_G8'
            )
            db.session.add(loc)
            db.session.commit()
        flash('Delivery confirmed. Awaiting receiving staff acknowledgement.', 'success')
    else:
        flash(f"Error: {msg}", 'danger')
        
    return redirect(url_for('rider.dashboard'))

@rider_bp.route('/rider/update-location', methods=['POST'])
@login_required
@role_required('RIDER', 'ADMIN')
def update_location():
    """
    Enables background AJAX location updates from the mobile interface.
    """
    data = request.get_json() or {}
    lat = data.get('latitude')
    lng = data.get('longitude')
    request_id = data.get('request_id')
    event_name = data.get('event_name', 'PERIODIC_UPDATE')
    
    if lat and lng:
        loc = LocationRecord(
            request_id=request_id,
            rider_id=current_user.id,
            latitude=float(lat),
            longitude=float(lng),
            event_name=event_name
        )
        db.session.add(loc)
        db.session.commit()
        return jsonify({'status': 'success', 'message': 'Location logged.'})
        
    return jsonify({'status': 'error', 'message': 'Invalid coordinates.'}), 400
