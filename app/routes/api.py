from flask import Blueprint, jsonify, request
from flask_login import login_required
from app.models import SampleRequest, Branch, User, LocationRecord
from app.services.tat_service import TATService

api_bp = Blueprint('api', __name__)

@api_bp.route('/api/requests')
@login_required
def get_requests():
    """
    Returns filtered lists of requests for the Live Operations Dashboard.
    """
    branch_id = request.args.get('branch_id')
    status = request.args.get('status')
    priority = request.args.get('priority')
    is_delayed_filter = request.args.get('delayed')
    
    query = SampleRequest.query
    
    if branch_id:
        query = query.filter_by(branch_id=int(branch_id))
    if status:
        query = query.filter_by(status=status)
    if priority:
        query = query.filter_by(priority=priority)
        
    requests = query.order_by(SampleRequest.created_at.desc()).all()
    
    data = []
    for req in requests:
        is_delayed, elapsed, limit = TATService.check_is_delayed(req)
        
        # Apply delay filter
        if is_delayed_filter == 'true' and not is_delayed:
            continue
        if is_delayed_filter == 'false' and is_delayed:
            continue
            
        # Determine courier/rider
        rider_name = "Unassigned"
        for task in req.tasks:
            if task.task_type in ['PICKUP', 'TRANSPORT'] and task.assigned_user_id:
                rider_name = task.assigned_user.name
                break
                
        data.append({
            'id': req.id,
            'patient_name': req.patient_name,
            'branch': req.branch.name,
            'rider': rider_name,
            'status': req.status,
            'priority': req.priority,
            'created_at': req.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'elapsed_minutes': round(elapsed, 1),
            'is_delayed': is_delayed
        })
        
    return jsonify(data)

@api_bp.route('/api/requests/map')
@login_required
def get_map_data():
    """
    Provides geo-coordinates for G-8 HQ, branch hubs, and active riders for Leaflet map displays.
    """
    # 1. G-8 HQ Lab
    g8_lab = {
        'name': 'G-8 Main Laboratory (HQ)',
        'latitude': 33.6811,
        'longitude': 73.0361,
        'type': 'HQ'
    }
    
    # 2. Associated Branch Hubs
    branches = Branch.query.all()
    branches_data = []
    for b in branches:
        if b.code == 'G8':
            continue
            
        # Find active requests awaiting pickup at this branch
        pending_count = SampleRequest.query.filter(
            SampleRequest.branch_id == b.id,
            SampleRequest.status.in_(['Pickup Requested', 'Rider Assigned'])
        ).count()
        
        branches_data.append({
            'name': b.name,
            'code': b.code,
            'latitude': b.latitude or 33.6800,
            'longitude': b.longitude or 73.0300,
            'pending_requests': pending_count,
            'type': 'branch'
        })
        
    # 3. Active Riders tracking (last event locations of in-transit requests)
    active_requests = SampleRequest.query.filter(
        SampleRequest.status.in_(['Rider Assigned', 'Sample Collected', 'Arrived at G-8'])
    ).all()
    
    riders_data = []
    processed_riders = set()
    for req in active_requests:
        latest_loc = LocationRecord.query.filter_by(request_id=req.id).order_by(LocationRecord.timestamp.desc()).first()
        if latest_loc and latest_loc.rider_id not in processed_riders:
            processed_riders.add(latest_loc.rider_id)
            riders_data.append({
                'rider_name': latest_loc.rider.name,
                'request_id': req.id,
                'status': req.status,
                'latitude': latest_loc.latitude,
                'longitude': latest_loc.longitude,
                'timestamp': latest_loc.timestamp.strftime('%H:%M:%S'),
                'type': 'rider'
            })
            
    return jsonify({
        'g8_lab': g8_lab,
        'branches': branches_data,
        'riders': riders_data
    })
