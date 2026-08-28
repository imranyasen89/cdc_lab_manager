from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app.utils.timezone import now_pkt
from app import db

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    email = db.Column(db.String(100), nullable=True)
    role = db.Column(db.String(50), nullable=False)  # SUPER_ADMIN, ADMIN, MANAGER, SUPERVISOR, BRANCH_STAFF, RIDER, LAB_STAFF, VERIFIER
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=True)
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=True)
    status = db.Column(db.Boolean, default=True)  # True = Active, False = Inactive
    joining_date = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, default=now_pkt)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def has_task_permission(self, permission):
        """Check if user has a specific task permission."""
        return any(tp.permission == permission for tp in self.task_permissions)

class Branch(db.Model):
    __tablename__ = 'branches'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(20), unique=True, nullable=False)  # e.g. G8, G11
    address = db.Column(db.String(255), nullable=True)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    
    users = db.relationship('User', backref='branch', lazy=True)
    requests = db.relationship('SampleRequest', backref='branch', lazy=True)

class Department(db.Model):
    __tablename__ = 'departments'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.String(255), nullable=True)
    
    users = db.relationship('User', backref='department', lazy=True)

class OutsourcedLab(db.Model):
    __tablename__ = 'outsourced_labs'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    contact_info = db.Column(db.String(255), nullable=True)
    address = db.Column(db.String(255), nullable=True)

class TATRule(db.Model):
    __tablename__ = 'tat_rules'
    
    id = db.Column(db.Integer, primary_key=True)
    priority = db.Column(db.String(50), unique=True, nullable=False)  # Emergency, Urgent, Routine
    max_tat_minutes = db.Column(db.Integer, nullable=False)
    description = db.Column(db.String(255), nullable=True)

class SampleRequest(db.Model):
    __tablename__ = 'sample_requests'
    
    id = db.Column(db.String(50), primary_key=True)  # e.g., CDC-G11-20260820-000123
    patient_name = db.Column(db.String(100), nullable=False)
    gender = db.Column(db.String(20), nullable=False)
    patient_id = db.Column(db.String(50), nullable=True)  # External MRN/Registration No
    priority = db.Column(db.String(50), nullable=False)  # Emergency, Urgent, Routine
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    special_instructions = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(50), nullable=False, default='Pickup Requested')
    created_at = db.Column(db.DateTime, default=now_pkt)
    updated_at = db.Column(db.DateTime, default=now_pkt, onupdate=now_pkt)
    
    created_by = db.relationship('User', backref='created_requests', foreign_keys=[created_by_id])
    samples = db.relationship('Sample', backref='request', cascade='all, delete-orphan')
    tasks = db.relationship('Task', backref='request', cascade='all, delete-orphan')
    history = db.relationship('StatusHistory', backref='request', order_by='StatusHistory.timestamp', cascade='all, delete-orphan')
    location_records = db.relationship('LocationRecord', backref='request', cascade='all, delete-orphan')

class Sample(db.Model):
    __tablename__ = 'samples'
    
    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.String(50), db.ForeignKey('sample_requests.id'), nullable=False)
    sample_type = db.Column(db.String(50), nullable=False)  # Blood, Urine, Swab, Sputum, etc.
    quantity = db.Column(db.Integer, default=1)

class Task(db.Model):
    __tablename__ = 'tasks'
    
    id = db.Column(db.Integer, primary_key=True)
    task_type = db.Column(db.String(50), nullable=False)  # PICKUP, TRANSPORT, RECEIVE, PROCESS, OUTSOURCE, ENTER_RESULT, VERIFY, DELIVER
    request_id = db.Column(db.String(50), db.ForeignKey('sample_requests.id'), nullable=False)
    assigned_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    assigned_role = db.Column(db.String(50), nullable=True)  # Broadcast to all with this role if user_id is null
    created_time = db.Column(db.DateTime, default=now_pkt)
    start_time = db.Column(db.DateTime, nullable=True)
    completion_time = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(50), default='PENDING')  # PENDING, IN_PROGRESS, COMPLETED, CANCELLED
    location = db.Column(db.String(255), nullable=True)
    remarks = db.Column(db.Text, nullable=True)
    
    assigned_user = db.relationship('User', backref='tasks')

class LocationRecord(db.Model):
    __tablename__ = 'location_records'
    
    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.String(50), db.ForeignKey('sample_requests.id'), nullable=True)
    rider_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    event_name = db.Column(db.String(100), nullable=False)  # ACCEPT_PICKUP, START_PICKUP, CONFIRM_COLLECTION, START_DELIVERY, ARRIVE_G8, etc.
    timestamp = db.Column(db.DateTime, default=now_pkt)
    
    rider = db.relationship('User', backref='location_records')

class StatusHistory(db.Model):
    __tablename__ = 'status_history'
    
    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.String(50), db.ForeignKey('sample_requests.id'), nullable=False)
    status = db.Column(db.String(50), nullable=False)
    changed_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=now_pkt)
    remarks = db.Column(db.Text, nullable=True)
    location = db.Column(db.String(255), nullable=True)
    
    changed_by = db.relationship('User', backref='status_changes')

class Notification(db.Model):
    __tablename__ = 'notifications'
    
    id = db.Column(db.Integer, primary_key=True)
    message = db.Column(db.String(255), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)  # Targeted user
    assigned_role = db.Column(db.String(50), nullable=True)  # Broad role notifications (e.g. RIDER, LAB_STAFF)
    is_read = db.Column(db.Boolean, default=False)
    priority = db.Column(db.String(20), default='Routine')  # Routine, Emergency
    request_id = db.Column(db.String(50), db.ForeignKey('sample_requests.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=now_pkt)
    
    user = db.relationship('User', backref='notifications')
    request = db.relationship('SampleRequest', backref='notifications')

class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    action = db.Column(db.String(100), nullable=False)
    request_id = db.Column(db.String(50), db.ForeignKey('sample_requests.id'), nullable=True)
    old_status = db.Column(db.String(50), nullable=True)
    new_status = db.Column(db.String(50), nullable=True)
    timestamp = db.Column(db.DateTime, default=now_pkt)
    ip_address = db.Column(db.String(50), nullable=True)
    location = db.Column(db.String(255), nullable=True)
    
    user = db.relationship('User', backref='audit_logs')

class StaffProfile(db.Model):
    __tablename__ = 'staff_profiles'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    designation = db.Column(db.String(100))
    overall_experience = db.Column(db.Float)  # years
    cdc_experience = db.Column(db.Float)      # years
    qualification = db.Column(db.String(100))
    other_certificates = db.Column(db.Text)
    sections_independent = db.Column(db.Text) # Chemistry, Hematology, etc.
    study_further = db.Column(db.String(50))   # Yes/No
    research_interest = db.Column(db.String(50)) # Yes/No
    training_requested = db.Column(db.Text)
    job_satisfaction = db.Column(db.String(100))
    positive_aspects = db.Column(db.Text)
    suggestions = db.Column(db.Text)
    
    user = db.relationship('User', backref=db.backref('staff_profile', uselist=False, lazy=True))

class StaffPerformanceReport(db.Model):
    __tablename__ = 'staff_performance_reports'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date = db.Column(db.Date, nullable=False, default=lambda: now_pkt().date())
    duty_status = db.Column(db.String(50), nullable=False, default='Present') # Present, On Leave, Off Duty
    shift = db.Column(db.String(50), nullable=True) # Morning, Evening, Night
    branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=True)
    section = db.Column(db.String(100), nullable=True) # Section worked in
    
    # Workload Counts
    patients_booked = db.Column(db.Integer, default=0)
    samples_collected = db.Column(db.Integer, default=0)
    tests_processed = db.Column(db.Integer, default=0) # Samples Processed
    results_entered = db.Column(db.Integer, default=0)
    samples_referred = db.Column(db.Integer, default=0)
    pending_work = db.Column(db.Integer, default=0)
    
    # Issues & Details
    qc_issue = db.Column(db.Boolean, default=False)
    qc_details = db.Column(db.Text, nullable=True)
    
    equipment_issue = db.Column(db.Boolean, default=False)
    equipment_details = db.Column(db.Text, nullable=True)
    
    additional_task = db.Column(db.Boolean, default=False)
    task_details = db.Column(db.Text, nullable=True)
    
    incident = db.Column(db.Boolean, default=False)
    incident_details = db.Column(db.Text, nullable=True)
    
    remarks = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=now_pkt)
    
    user = db.relationship('User', backref=db.backref('staff_reports', lazy=True))
    branch = db.relationship('Branch', backref=db.backref('staff_reports', lazy=True))

class UserTaskPermission(db.Model):
    """Granular task-based permissions for specific lab workflows."""
    __tablename__ = 'user_task_permissions'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    permission = db.Column(db.String(50), nullable=False)
    # Permissions: SAMPLE_RECEIVING, PROCESSING, RESULT_ENTRY, VERIFICATION
    
    user = db.relationship('User', backref='task_permissions')
    
    # Unique constraint: each user can have each permission only once
    __table_args__ = (db.UniqueConstraint('user_id', 'permission', name='uq_user_permission'),)

class CenterDistance(db.Model):
    """Stores known distances (km) between branch centers."""
    __tablename__ = 'center_distances'
    
    id = db.Column(db.Integer, primary_key=True)
    from_branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=False)
    to_branch_id = db.Column(db.Integer, db.ForeignKey('branches.id'), nullable=False)
    distance_km = db.Column(db.Float, nullable=False)
    is_manual = db.Column(db.Boolean, default=True)  # True = manual input, False = auto-calculated
    
    from_branch = db.relationship('Branch', foreign_keys=[from_branch_id], backref='distances_from')
    to_branch = db.relationship('Branch', foreign_keys=[to_branch_id], backref='distances_to')
    
    __table_args__ = (db.UniqueConstraint('from_branch_id', 'to_branch_id', name='uq_center_distance'),)

