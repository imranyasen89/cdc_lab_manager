from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app import db
from app.models import SampleRequest, Sample, Task, StatusHistory, AuditLog, TATRule, Branch, User
from app.utils.decorators import role_required
from app.utils.validation import form_int, to_int, InputError
from app.utils.containers import CONTAINERS, CONDITIONS
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
    branches = Branch.query.order_by(Branch.name).all()
    user_branch = current_user.branch
    priorities = TATRule.query.all()
    riders = User.query.filter_by(role='RIDER', status=True).order_by(User.name).all()

    def render_form():
        return render_template('branch/create_request.html', priorities=priorities, branches=branches,
                               user_branch=user_branch, riders=riders, containers=CONTAINERS,
                               conditions=CONDITIONS)

    if request.method == 'GET':
        return render_form()

    if current_user.role in ['ADMIN', 'SUPER_ADMIN', 'MANAGER']:
        branch_id = request.form.get('branch_id')
        branch = db.session.get(Branch, to_int(branch_id, 'branch')) if branch_id else None
    else:
        branch = user_branch
    if not branch:
        flash('A valid branch must be selected to create a request.', 'danger')
        return redirect(url_for('branch.dashboard'))

    patients = _parse_patient_rows()
    if not patients:
        flash('Add at least one patient with a name, tests and at least one sample.', 'danger')
        return render_form()

    handed_over_to = (request.form.get('handed_over_to') or '').strip() or None
    batch_note = (request.form.get('special_instructions') or '').strip() or None
    now = now_pkt()
    batch_id = generate_batch_id(branch.code) if len(patients) > 1 else None
    created_ids = []

    for p in patients:
        request_id = generate_request_id(branch.code)
        notes = ' | '.join(x for x in [p['remarks'], batch_note] if x) or None
        req = SampleRequest(
            id=request_id, patient_name=p['name'], gender=p['gender'], patient_id=p['mrn'],
            patient_age=p['age'], test_requested=p['tests'], priority=p['priority'],
            branch=branch, created_by_id=current_user.id, special_instructions=notes,
            status='Pickup Requested', batch_id=batch_id,
            handed_over_to=handed_over_to, handed_over_at=now if handed_over_to else None,
        )
        db.session.add(req)
        db.session.flush()

        for s in p['samples']:
            db.session.add(Sample(request_id=request_id, sample_type=s['sample_type'], container=s['container'],
                                  quantity=s['quantity'], condition=p['condition'], remarks=p['remarks']))
        sample_summary = ', '.join(f"{s['quantity']}x {s['label']}" for s in p['samples'])

        db.session.add(StatusHistory(
            request_id=request_id, status='Pickup Requested', changed_by_id=current_user.id,
            remarks=(f"Request created. Tests: {p['tests']}. Samples: {sample_summary}. Condition: {p['condition']}"
                     + (f". Handed over to: {handed_over_to}" if handed_over_to else '')),
            location=branch.name))
        db.session.add(AuditLog(
            user_id=current_user.id, action="REQUEST_CREATE", request_id=request_id, old_status=None,
            new_status="Pickup Requested", location=branch.name, ip_address=request.remote_addr))
        db.session.add(Task(
            task_type='PICKUP', request_id=request_id, assigned_role='RIDER', status='PENDING',
            location=branch.name, remarks=f"Collect: {sample_summary}"))
        WorkflowService._send_notifications(req, None, 'Pickup Requested', current_user, None)
        created_ids.append(request_id)

    db.session.commit()
    if len(created_ids) == 1:
        flash(f"Pickup request {created_ids[0]} created successfully.", 'success')
    else:
        flash(f"Batch {batch_id}: {len(created_ids)} patient requests created "
              f"({created_ids[0]} … {created_ids[-1]}).", 'success')
    return redirect(url_for('branch.dashboard'))


def generate_batch_id(branch_code):
    """BATCH-<BranchCode>-<YYYYMMDD>-<Seq> grouping patients dispatched together."""
    code_clean = (branch_code or 'HQ').strip().replace(' ', '').upper()
    prefix = f"BATCH-{code_clean}-{now_pkt().strftime('%Y%m%d')}-"
    used = db.session.query(SampleRequest.batch_id).filter(SampleRequest.batch_id.like(f"{prefix}%")).distinct().all()
    seq = max([int(b.rsplit('-', 1)[-1]) for (b,) in used if b and b.rsplit('-', 1)[-1].isdigit()] or [0]) + 1
    return f"{prefix}{seq:03d}"


def _parse_patient_rows():
    """Read patient rows (p-<n>-<field>) from the form; falls back to the old single-patient fields."""
    form = request.form
    indexes = sorted({int(k.split('-')[1]) for k in form if k.startswith('p-') and k.split('-')[1].isdigit()})
    rows = []
    if indexes:
        for i in indexes:
            get = lambda f, d='': (form.get(f'p-{i}-{f}') or d).strip()
            samples = []
            for code, label, sample_type, _color, _tests in CONTAINERS:
                qty = get(f'qty-{code}', '0') or '0'
                if not qty.isdigit():
                    raise InputError(f"{label}: quantity must be a whole number.")
                qty = min(int(qty), 50)
                if qty <= 0:
                    continue
                if code == 'OTHER':
                    other = get('other') or 'Other'
                    samples.append({'container': code, 'sample_type': other[:50], 'label': other, 'quantity': qty})
                else:
                    samples.append({'container': code, 'sample_type': sample_type, 'label': label, 'quantity': qty})
            name = get('name')
            if not name and not samples and not get('tests') and not get('mrn'):
                continue  # completely empty row
            if not name:
                raise InputError(f"Patient row {len(rows) + 1}: patient name is required.")
            if not get('tests'):
                raise InputError(f"Patient '{name}': enter the tests requested.")
            if not samples:
                raise InputError(f"Patient '{name}': select at least one sample / vial.")
            condition = get('condition', 'Good')
            rows.append({
                'name': name, 'mrn': get('mrn') or None, 'age': get('age') or None,
                'gender': get('gender', 'Male'), 'tests': get('tests'),
                'priority': get('priority', 'Routine'), 'condition': condition if condition in CONDITIONS else 'Good',
                'remarks': get('remarks') or None, 'samples': samples,
            })
        return rows

    # Legacy single-patient form fields
    name = (form.get('patient_name') or '').strip()
    types = form.getlist('sample_types') or ([form.get('sample_type')] if form.get('sample_type') else [])
    other = (form.get('other_sample_type') or '').strip()
    types = [other if t == 'Other' and other else t for t in types if t != 'Other' or other]
    if not name or not types:
        return []
    qty = form_int('quantity', 1, minimum=1)
    by_type = {c[2]: c for c in CONTAINERS}
    samples = [{'container': by_type[t][0] if t in by_type else 'OTHER', 'sample_type': t, 'label': t,
                'quantity': qty} for t in types]
    return [{'name': name, 'mrn': (form.get('patient_id') or '').strip() or None, 'age': None,
             'gender': form.get('gender', 'Male'), 'tests': (form.get('test_requested') or '').strip(),
             'priority': form.get('priority', 'Routine'), 'condition': 'Good', 'remarks': None,
             'samples': samples}]
