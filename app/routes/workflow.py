from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required
from app.models import SampleRequest, LocationRecord, Branch, User
from app.services.tat_service import TATService

workflow_bp = Blueprint('workflow', __name__)

@workflow_bp.route('/request/<request_id>')
@login_required
def detail(request_id):
    req = SampleRequest.query.filter_by(id=request_id).first_or_404()
    
    # Calculate TAT statistics
    durations = TATService.get_stage_durations(req)
    is_delayed, elapsed, limit = TATService.check_is_delayed(req)
    
    # Fetch geographic path records
    locations = LocationRecord.query.filter_by(request_id=req.id).order_by(LocationRecord.timestamp.asc()).all()
    
    return render_template(
        'workflow/detail.html',
        sample_request=req,
        durations=durations,
        is_delayed=is_delayed,
        elapsed=elapsed,
        limit=limit,
        locations=locations
    )

@workflow_bp.route('/search')
@login_required
def search():
    query = request.args.get('query', '').strip()
    results = []
    
    if query:
        # Search by ID, Patient name, patient MRN, status, branch code, or priority
        results = SampleRequest.query.join(Branch).outerjoin(User, SampleRequest.created_by_id == User.id).filter(
            (SampleRequest.id.like(f"%{query}%")) |
            (SampleRequest.patient_name.like(f"%{query}%")) |
            (SampleRequest.patient_id.like(f"%{query}%")) |
            (SampleRequest.status.like(f"%{query}%")) |
            (SampleRequest.priority.like(f"%{query}%")) |
            (Branch.name.like(f"%{query}%")) |
            (User.name.like(f"%{query}%"))
        ).order_by(SampleRequest.created_at.desc()).all()
        
    return render_template('workflow/search.html', query=query, results=results)
