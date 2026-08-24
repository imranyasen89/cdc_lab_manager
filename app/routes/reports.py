from flask import Blueprint, render_template, request, Response, flash, redirect, url_for
from flask_login import login_required, current_user
from app.models import SampleRequest, User, Branch, TATRule, Task, LocationRecord, StaffProfile, StaffPerformanceReport
from app.services.tat_service import TATService
from app.services.distance_service import DistanceService
from app.utils.timezone import now_pkt
from app.utils.decorators import role_required
from app import db
from datetime import datetime, timedelta
from collections import defaultdict
import csv
import io

reports_bp = Blueprint('reports', __name__)

@reports_bp.route('/reports/daily')
@login_required
def daily_report():
    # Filter by date, defaults to today (Pakistan time)
    date_str = request.args.get('date', now_pkt().strftime('%Y-%m-%d'))
    try:
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        target_date = now_pkt().date()
        date_str = target_date.strftime('%Y-%m-%d')
        
    # Start and end of day
    start_dt = datetime.combine(target_date, datetime.min.time())
    end_dt = datetime.combine(target_date, datetime.max.time())
    
    requests = SampleRequest.query.filter(SampleRequest.created_at.between(start_dt, end_dt)).all()
    
    # Stats
    total = len(requests)
    collected = sum(1 for r in requests if r.status not in ['Pickup Requested', 'Rider Assigned'])
    received = sum(1 for r in requests if r.status not in ['Pickup Requested', 'Rider Assigned', 'Sample Collected', 'Arrived at G-8'])
    processed = sum(1 for r in requests if r.status in ['Processing Completed', 'Result Pending Entry', 'Pending Verification', 'Verified', 'Completed'])
    verified = sum(1 for r in requests if r.status in ['Verified', 'Completed'])
    delivered = sum(1 for r in requests if r.status == 'Completed')
    
    pending = sum(1 for r in requests if r.status != 'Completed')
    
    delayed_count = 0
    for r in requests:
        is_delayed, _, _ = TATService.check_is_delayed(r)
        if is_delayed:
            delayed_count += 1
            
    stats = {
        'total': total,
        'collected': collected,
        'received': received,
        'processed': processed,
        'verified': verified,
        'delivered': delivered,
        'pending': pending,
        'delayed': delayed_count
    }
    
    return render_template('reports/daily.html', stats=stats, date=date_str)

def get_performance_data(preset, start_date_str, end_date_str):
    today = now_pkt().date()
    
    if preset == 'today':
        start_date = today
        end_date = today
    elif preset == 'weekly':
        start_date = today - timedelta(days=6)
        end_date = today
    elif preset == 'monthly':
        start_date = today - timedelta(days=29)
        end_date = today
    elif preset == 'custom':
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            preset = 'weekly'
            start_date = today - timedelta(days=6)
            end_date = today
    else:
        preset = 'weekly'
        start_date = today - timedelta(days=6)
        end_date = today

    start_dt = datetime.combine(start_date, datetime.min.time())
    end_dt = datetime.combine(end_date, datetime.max.time())
    
    requests = SampleRequest.query.filter(SampleRequest.created_at.between(start_dt, end_dt)).all()
    
    location_records = LocationRecord.query.filter(
        LocationRecord.timestamp.between(start_dt, end_dt)
    ).order_by(LocationRecord.timestamp.asc()).all()
    
    rider_daily_locations = defaultdict(list)
    for rec in location_records:
        rec_date = rec.timestamp.date()
        rider_daily_locations[(rec.rider_id, rec_date)].append(rec)
        
    rider_daily_distances = {}
    for key, recs in rider_daily_locations.items():
        dist = 0.0
        for i in range(len(recs) - 1):
            dist += DistanceService.calculate_distance(
                recs[i].latitude, recs[i].longitude,
                recs[i+1].latitude, recs[i+1].longitude
            )
        rider_daily_distances[key] = round(dist, 2)
        
    requests_by_date = defaultdict(list)
    for req in requests:
        req_date = req.created_at.date()
        requests_by_date[req_date].append(req)
        
    riders = User.query.filter_by(role='RIDER').all()
    
    riders_summary = {}
    for r in riders:
        riders_summary[r.id] = {
            'id': r.id,
            'name': r.name,
            'emp_id': r.employee_id,
            'handled': 0,
            'pickup_times': [],
            'transport_times': [],
            'delays': 0,
            'total_distance': 0.0
        }
        
    daily_performance = []
    
    delta = end_date - start_date
    dates = [start_date + timedelta(days=i) for i in range(delta.days + 1)]
    
    for d in dates:
        for r in riders:
            handled_requests = []
            pickup_times = []
            transport_times = []
            delays = 0
            
            for req in requests_by_date[d]:
                rider_assigned = False
                for task in req.tasks:
                    if task.task_type in ['PICKUP', 'TRANSPORT'] and task.assigned_user_id == r.id:
                        rider_assigned = True
                        break
                if rider_assigned:
                    handled_requests.append(req)
                    durations = TATService.get_stage_durations(req)
                    is_delayed, _, _ = TATService.check_is_delayed(req)
                    if is_delayed:
                        delays += 1
                    if durations['pickup_response'] is not None:
                        pickup_times.append(durations['pickup_response'])
                    if durations['transport'] is not None:
                        transport_times.append(durations['transport'])
                        
            distance = rider_daily_distances.get((r.id, d), 0.0)
            
            if len(handled_requests) > 0 or distance > 0.0:
                avg_pickup = round(sum(pickup_times) / len(pickup_times), 1) if pickup_times else 0.0
                avg_transport = round(sum(transport_times) / len(transport_times), 1) if transport_times else 0.0
                
                daily_performance.append({
                    'date': d.strftime('%Y-%m-%d'),
                    'rider_id': r.id,
                    'name': r.name,
                    'emp_id': r.employee_id,
                    'handled': len(handled_requests),
                    'avg_pickup': avg_pickup,
                    'avg_transport': avg_transport,
                    'distance': distance,
                    'delays': delays
                })
                
                r_sum = riders_summary[r.id]
                r_sum['handled'] += len(handled_requests)
                r_sum['delays'] += delays
                r_sum['total_distance'] += distance
                r_sum['pickup_times'].extend(pickup_times)
                r_sum['transport_times'].extend(transport_times)
                
    def calculate_avg(lst):
        return round(sum(lst) / len(lst), 1) if lst else 0.0
        
    for rid, rdata in riders_summary.items():
        rdata['avg_pickup'] = calculate_avg(rdata['pickup_times'])
        rdata['avg_transport'] = calculate_avg(rdata['transport_times'])
        rdata['total_distance'] = round(rdata['total_distance'], 2)
        
    branches_data = {}
    branches = Branch.query.all()
    for b in branches:
        branches_data[b.id] = {
            'name': b.name,
            'code': b.code,
            'generated': 0,
            'total_samples': 0,
            'pickup_times': [],
            'transport_times': [],
            'delays': 0
        }
        
    for req in requests:
        is_delayed, _, _ = TATService.check_is_delayed(req)
        durations = TATService.get_stage_durations(req)
        
        if req.branch_id in branches_data:
            bdata = branches_data[req.branch_id]
            bdata['generated'] += 1
            bdata['total_samples'] += sum(s.quantity for s in req.samples)
            if is_delayed:
                bdata['delays'] += 1
            if durations['branch_pickup'] is not None:
                bdata['pickup_times'].append(durations['branch_pickup'])
            if durations['transport'] is not None:
                bdata['transport_times'].append(durations['transport'])
                
    for bid, bdata in branches_data.items():
        bdata['avg_pickup'] = calculate_avg(bdata['pickup_times'])
        bdata['avg_transport'] = calculate_avg(bdata['transport_times'])
        
    lab_data = {
        'receiving_tats': [],
        'processing_tats': [],
        'verification_tats': [],
        'overall_tats': [],
        'total_requests': len(requests),
        'delayed_requests': 0
    }
    
    for req in requests:
        is_delayed, _, _ = TATService.check_is_delayed(req)
        durations = TATService.get_stage_durations(req)
        if is_delayed:
            lab_data['delayed_requests'] += 1
        if durations['receiving_delay'] is not None:
            lab_data['receiving_tats'].append(durations['receiving_delay'])
        if durations['processing'] is not None:
            lab_data['processing_tats'].append(durations['processing'])
        if durations['verification'] is not None:
            lab_data['verification_tats'].append(durations['verification'])
        if durations['total_tat'] is not None:
            lab_data['overall_tats'].append(durations['total_tat'])
            
    lab_averages = {
        'avg_receiving': calculate_avg(lab_data['receiving_tats']),
        'avg_processing': calculate_avg(lab_data['processing_tats']),
        'avg_verification': calculate_avg(lab_data['verification_tats']),
        'avg_overall': calculate_avg(lab_data['overall_tats']),
        'total': lab_data['total_requests'],
        'delayed': lab_data['delayed_requests']
    }
    
    daily_performance.sort(key=lambda x: (x['date'], x['name']), reverse=True)
    
    return {
        'preset': preset,
        'start_date': start_date.strftime('%Y-%m-%d'),
        'end_date': end_date.strftime('%Y-%m-%d'),
        'requests': requests,
        'riders_summary': list(riders_summary.values()),
        'daily_performance': daily_performance,
        'branches': list(branches_data.values()),
        'lab': lab_averages
    }

@reports_bp.route('/reports/performance')
@login_required
def performance():
    preset = request.args.get('preset', 'weekly')
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    
    data = get_performance_data(preset, start_date_str, end_date_str)
    
    return render_template(
        'reports/performance.html',
        preset=data['preset'],
        start_date=data['start_date'],
        end_date=data['end_date'],
        riders=data['riders_summary'],
        daily_performance=data['daily_performance'],
        branches=data['branches'],
        lab=data['lab']
    )

@reports_bp.route('/reports/export/<report_type>')
@login_required
def export_report(report_type):
    preset = request.args.get('preset', 'weekly')
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    if report_type == 'daily':
        date_str = request.args.get('date')
        if date_str:
            try:
                target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                target_date = now_pkt().date()
        else:
            target_date = now_pkt().date()
            
        start_dt = datetime.combine(target_date, datetime.min.time())
        end_dt = datetime.combine(target_date, datetime.max.time())
        
        requests = SampleRequest.query.filter(SampleRequest.created_at.between(start_dt, end_dt)).order_by(SampleRequest.created_at.desc()).all()
        
        writer.writerow(['Request ID', 'Branch', 'Patient Name', 'Gender', 'Priority', 'Status', 'Created At (PKT)', 'Total TAT (min)', 'Delayed'])
        for req in requests:
            durations = TATService.get_stage_durations(req)
            is_delayed, _, _ = TATService.check_is_delayed(req)
            writer.writerow([
                req.id,
                req.branch.name,
                req.patient_name,
                req.gender,
                req.priority,
                req.status,
                req.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                durations['total_tat'] or '',
                'Yes' if is_delayed else 'No'
            ])
            
    elif report_type == 'rider':
        data = get_performance_data(preset, start_date_str, end_date_str)
        writer.writerow(['Date', 'Rider Name', 'Employee ID', 'Tasks Handled', 'Distance Covered (km)', 'Avg Pickup Response (min)', 'Avg Transport Time (min)', 'TAT Violations'])
        for row in data['daily_performance']:
            writer.writerow([
                row['date'],
                row['name'],
                row['emp_id'],
                row['handled'],
                row['distance'],
                row['avg_pickup'],
                row['avg_transport'],
                row['delays']
            ])
            
    elif report_type == 'branch':
        data = get_performance_data(preset, start_date_str, end_date_str)
        writer.writerow(['Branch Code', 'Branch Name', 'Total Requests Generated', 'Total Samples/Tests', 'Avg Pickup Time (min)', 'Avg Transport Time (min)', 'TAT Violations'])
        for row in data['branches']:
            writer.writerow([
                row['code'],
                row['name'],
                row['generated'],
                row['total_samples'],
                row['avg_pickup'],
                row['avg_transport'],
                row['delays']
            ])
            
    response = Response(output.getvalue(), mimetype='text/csv')
    response.headers['Content-Disposition'] = f'attachment; filename={report_type}_report_{now_pkt().strftime("%Y%m%d")}.csv'
    return response

@reports_bp.route('/reports/staff/dashboard')
@login_required
def staff_dashboard():
    # Load or initialize blank staff profile
    profile = StaffProfile.query.filter_by(user_id=current_user.id).first()
    if not profile:
        profile = StaffProfile(
            user_id=current_user.id,
            designation=current_user.role.replace('_', ' ').title(),
            overall_experience=0.0,
            cdc_experience=0.0,
            qualification='Not Set',
            sections_independent='None',
            study_further='No',
            research_interest='No'
        )
        db.session.add(profile)
        db.session.commit()
        
    branches = Branch.query.all()
    # Fetch past daily reports
    my_reports = StaffPerformanceReport.query.filter_by(user_id=current_user.id).order_by(StaffPerformanceReport.date.desc()).all()
    
    # Tests processed chart data (last 7 reports)
    chart_reports = list(reversed(my_reports[:7]))
    chart_dates = [r.date.strftime('%b %d') for r in chart_reports]
    chart_tests = [r.tests_processed for r in chart_reports]
    
    return render_template(
        'reports/staff_dashboard.html',
        profile=profile,
        branches=branches,
        my_reports=my_reports,
        chart_dates=chart_dates,
        chart_tests=chart_tests,
        today=now_pkt().strftime('%Y-%m-%d'),
        now_pkt=now_pkt
    )

@reports_bp.route('/reports/staff/submit', methods=['POST'])
@login_required
def staff_submit_report():
    shift = request.form.get('shift', 'Morning')
    branch_id = request.form.get('branch_id', type=int)
    sections_selected = request.form.getlist('sections')
    section = ", ".join(sections_selected) if sections_selected else 'None'
    tests_processed = request.form.get('tests_processed', 0, type=int)
    tasks_completed = request.form.get('tasks_completed', '')
    challenges = request.form.get('challenges', '')
    satisfaction = request.form.get('satisfaction', 'Satisfied')
    training_needs = request.form.get('training_needs', '')
    suggestions = request.form.get('suggestions', '')
    
    date_str = request.form.get('date')
    if date_str:
        try:
            report_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            report_date = now_pkt().date()
    else:
        report_date = now_pkt().date()
        
    # Check if a report already exists for this date and user
    existing = StaffPerformanceReport.query.filter_by(user_id=current_user.id, date=report_date).first()
    if existing:
        flash(f"A report has already been submitted for {report_date}.", 'warning')
        return redirect(url_for('reports.staff_dashboard'))
        
    report = StaffPerformanceReport(
        user_id=current_user.id,
        date=report_date,
        shift=shift,
        branch_id=branch_id,
        section=section,
        tests_processed=tests_processed,
        tasks_completed=tasks_completed,
        challenges=challenges,
        satisfaction=satisfaction,
        training_needs=training_needs,
        suggestions=suggestions
    )
    db.session.add(report)
    db.session.commit()
    
    flash("Daily performance report submitted successfully.", "success")
    return redirect(url_for('reports.staff_dashboard'))

@reports_bp.route('/reports/staff/profile/update', methods=['POST'])
@login_required
def staff_profile_update():
    profile = StaffProfile.query.filter_by(user_id=current_user.id).first()
    if not profile:
        profile = StaffProfile(user_id=current_user.id)
        db.session.add(profile)
        
    profile.designation = request.form.get('designation', '')
    profile.overall_experience = request.form.get('overall_experience', 0.0, type=float)
    profile.cdc_experience = request.form.get('cdc_experience', 0.0, type=float)
    profile.qualification = request.form.get('qualification', '')
    profile.other_certificates = request.form.get('other_certificates', '')
    
    sections_selected = request.form.getlist('sections')
    profile.sections_independent = ", ".join(sections_selected) if sections_selected else 'None'
    
    profile.study_further = request.form.get('study_further', 'No')
    profile.research_interest = request.form.get('research_interest', 'No')
    profile.training_requested = request.form.get('training_requested', '')
    
    db.session.commit()
    flash("Skills profile updated successfully.", "success")
    return redirect(url_for('reports.staff_dashboard'))

@reports_bp.route('/reports/staff/admin')
@login_required
@role_required('ADMIN', 'MANAGER', 'SUPERVISOR')
def staff_admin():
    # Load all submissions
    reports = StaffPerformanceReport.query.order_by(StaffPerformanceReport.date.desc()).all()
    
    # Load all profiles
    profiles = StaffProfile.query.all()
    
    # Aggregates
    total_tests = sum(r.tests_processed for r in reports)
    total_submissions = len(reports)
    
    # Satisfaction counters
    satisfaction_counts = {'Satisfied': 0, 'Neutral': 0, 'Dissatisfied': 0}
    for r in reports:
        sat = r.satisfaction or 'Satisfied'
        if sat in satisfaction_counts:
            satisfaction_counts[sat] += 1
            
    # Branch breakdown of tests processed
    branch_tests = defaultdict(int)
    for r in reports:
        branch_tests[r.branch.name] += r.tests_processed
        
    # Section breakdown of tests processed
    section_tests = defaultdict(int)
    for r in reports:
        sections = [s.strip() for s in r.section.split(',')]
        for sec in sections:
            if sec and sec != 'None':
                section_tests[sec] += r.tests_processed
                
    # Format charts
    branch_chart_labels = list(branch_tests.keys())
    branch_chart_values = list(branch_tests.values())
    
    section_chart_labels = list(section_tests.keys())
    section_chart_values = list(section_tests.values())
    
    recent_submissions = reports[:15]
    
    return render_template(
        'reports/staff_admin.html',
        reports=reports,
        profiles=profiles,
        total_tests=total_tests,
        total_submissions=total_submissions,
        satisfaction=satisfaction_counts,
        branch_labels=branch_chart_labels,
        branch_values=branch_chart_values,
        section_labels=section_chart_labels,
        section_values=section_chart_values,
        recent_submissions=recent_submissions
    )
