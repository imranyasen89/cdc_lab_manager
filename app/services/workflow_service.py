from app.utils.timezone import now_pkt
from app import db
from app.models import SampleRequest, StatusHistory, AuditLog, Task, User, Branch
from app.services.notification_service import NotificationService

class WorkflowService:
    # State transitions: current_status -> list of next valid statuses
    TRANSITIONS = {
        'Pickup Requested': ['Rider Assigned'],
        'Rider Assigned': ['Sample Collected', 'Pickup Requested'],
        'Sample Collected': ['Arrived at G-8'],
        'Arrived at G-8': ['Received at G-8'],
        'Received at G-8': ['Processing', 'Outsource Requested'],
        'Processing': ['Processing Completed'],
        # Processing Completed goes directly to result entry (Pending Verification)
        'Processing Completed': ['Pending Verification'],
        
        # Outsource flow
        'Outsource Requested': ['Sent to Outsourced Lab'],
        'Sent to Outsourced Lab': ['Outsourced Result Received'],
        # Outsourced Result Received also goes to result entry
        'Outsourced Result Received': ['Pending Verification'],
        
        # Verification & Delivery
        'Pending Verification': ['Verified', 'Correction Required'],
        # Correction Required sends back to result entry (re-enter results)
        'Correction Required': ['Pending Verification'],
        'Verified': ['Completed']
    }
    
    # Authorized roles for each target status
    ROLE_PERMISSIONS = {
        'Pickup Requested': ['BRANCH_STAFF', 'SUPERVISOR', 'MANAGER', 'ADMIN'],
        'Rider Assigned': ['RIDER', 'SUPERVISOR', 'MANAGER', 'ADMIN'],
        'Sample Collected': ['RIDER', 'ADMIN'],
        'Arrived at G-8': ['RIDER', 'ADMIN'],
        'Received at G-8': ['LAB_STAFF', 'SUPERVISOR', 'MANAGER', 'ADMIN'],
        'Processing': ['LAB_STAFF', 'ADMIN'],
        'Processing Completed': ['LAB_STAFF', 'ADMIN'],
        'Outsource Requested': ['LAB_STAFF', 'SUPERVISOR', 'MANAGER', 'ADMIN'],
        'Sent to Outsourced Lab': ['RIDER', 'LAB_STAFF', 'SUPERVISOR', 'MANAGER', 'ADMIN'],
        'Outsourced Result Received': ['LAB_STAFF', 'SUPERVISOR', 'MANAGER', 'ADMIN'],
        'Pending Verification': ['LAB_STAFF', 'ADMIN'],
        'Verified': ['VERIFIER', 'SUPERVISOR', 'MANAGER', 'ADMIN'],
        'Correction Required': ['VERIFIER', 'SUPERVISOR', 'MANAGER', 'ADMIN'],
        'Completed': ['BRANCH_STAFF', 'LAB_STAFF', 'RECEPTION_STAFF', 'SUPERVISOR', 'MANAGER', 'ADMIN']
    }

    @staticmethod
    def transition_to(request_id, new_status, user, remarks=None, location=None, ip_address=None, extra_data=None):
        """
        Transition a request to a new status.
        Uses database transaction locks to prevent concurrency issues (e.g. duplicate rider self-assignment).
        """
        extra_data = extra_data or {}
        
        # Lock request row to prevent race conditions
        req = SampleRequest.query.filter_by(id=request_id).with_for_update().first()
        if not req:
            return False, "Sample Request not found."
            
        old_status = req.status
        
        # Guard: check if transition is allowed
        if new_status not in WorkflowService.TRANSITIONS.get(old_status, []):
            return False, f"Workflow transition from '{old_status}' to '{new_status}' is invalid."
            
        # Guard: check authorization
        allowed_roles = WorkflowService.ROLE_PERMISSIONS.get(new_status, [])
        if user.role not in allowed_roles:
            return False, f"Your role ({user.role}) is not authorized to transition requests to '{new_status}'."
            
        # Concurrency / state validation guards
        if new_status == 'Rider Assigned':
            rider_id = extra_data.get('rider_id')
            if not rider_id:
                return False, "Rider ID must be specified when assigning a rider."
            rider = User.query.get(rider_id)
            if not rider or rider.role != 'RIDER':
                return False, "Selected user is not a Rider."
                
            # If rider is self-assigning, verify that they are active
            if extra_data.get('method') == 'Self Assigned' and not rider.status:
                return False, "Your account is currently inactive."
                
        # Perform status update
        req.status = new_status
        req.updated_at = now_pkt()
        
        # Record Status History
        history = StatusHistory(
            request_id=req.id,
            status=new_status,
            changed_by_id=user.id,
            timestamp=now_pkt(),
            remarks=remarks,
            location=location
        )
        db.session.add(history)
        
        # Record Audit Log
        audit = AuditLog(
            user_id=user.id,
            action=f"TRANSITION_{new_status.upper().replace(' ', '_')}",
            request_id=req.id,
            old_status=old_status,
            new_status=new_status,
            timestamp=now_pkt(),
            ip_address=ip_address,
            location=location
        )
        db.session.add(audit)
        
        # Update associated generic tasks
        WorkflowService._update_tasks(req, old_status, new_status, user, remarks, location, extra_data)
        
        # Dispatch notifications
        WorkflowService._send_notifications(req, old_status, new_status, user, extra_data)
        
        try:
            db.session.commit()
            return True, "Transition successful."
        except Exception as e:
            db.session.rollback()
            return False, f"Database transaction failed: {str(e)}"

    @staticmethod
    def _update_tasks(req, old_status, new_status, user, remarks, location, extra_data):
        """
        Updates active tasks and automatically schedules subsequent workflow tasks.
        """
        now = now_pkt()
        
        # 1. Close current active task
        active_task = Task.query.filter_by(request_id=req.id, status='IN_PROGRESS').first()
        if not active_task:
            active_task = Task.query.filter_by(request_id=req.id, status='PENDING').first()
            
        if active_task:
            active_task.status = 'COMPLETED'
            active_task.completion_time = now
            if not active_task.assigned_user_id:
                active_task.assigned_user_id = user.id
                
        # 2. Schedule next task based on the target status
        if new_status == 'Rider Assigned':
            rider_id = extra_data.get('rider_id')
            task = Task(
                task_type='PICKUP',
                request_id=req.id,
                assigned_user_id=rider_id,
                created_time=now,
                start_time=now,
                status='IN_PROGRESS',
                location=location,
                remarks=f"Assignment Method: {extra_data.get('method', 'Lab Assigned')}"
            )
            db.session.add(task)
            
        elif new_status == 'Sample Collected':
            task = Task(
                task_type='TRANSPORT',
                request_id=req.id,
                assigned_user_id=user.id,
                created_time=now,
                start_time=now,
                status='IN_PROGRESS',
                location=location,
                remarks=remarks
            )
            db.session.add(task)
            
        elif new_status == 'Arrived at G-8':
            task = Task(
                task_type='RECEIVE',
                request_id=req.id,
                assigned_role='LAB_STAFF',
                created_time=now,
                status='PENDING',
                location=location,
                remarks=remarks
            )
            db.session.add(task)
            
        elif new_status == 'Received at G-8':
            # Create process task
            task = Task(
                task_type='PROCESS',
                request_id=req.id,
                assigned_role='LAB_STAFF',
                created_time=now,
                status='PENDING',
                location="G-8 Main Lab",
                remarks=remarks
            )
            db.session.add(task)
            
        elif new_status == 'Processing':
            task = Task(
                task_type='PROCESS',
                request_id=req.id,
                assigned_user_id=user.id,
                created_time=now,
                start_time=now,
                status='IN_PROGRESS',
                location="G-8 Main Lab",
                remarks=remarks
            )
            db.session.add(task)
            
        elif new_status == 'Processing Completed':
            # Lab staff will now enter results (Pending Verification stage)
            task = Task(
                task_type='ENTER_RESULT',
                request_id=req.id,
                assigned_role='LAB_STAFF',
                created_time=now,
                status='PENDING',
                remarks=remarks
            )
            db.session.add(task)
            
        elif new_status == 'Outsource Requested':
            task = Task(
                task_type='OUTSOURCE',
                request_id=req.id,
                assigned_role='LAB_STAFF',
                created_time=now,
                status='PENDING',
                remarks=f"Outsource Lab: {extra_data.get('outsourced_lab')}"
            )
            db.session.add(task)
            
        elif new_status == 'Sent to Outsourced Lab':
            task = Task(
                task_type='OUTSOURCE',
                request_id=req.id,
                assigned_user_id=user.id,
                created_time=now,
                start_time=now,
                status='IN_PROGRESS',
                remarks=remarks
            )
            db.session.add(task)
            
        elif new_status == 'Outsourced Result Received':
            # Lab staff will now enter results (Pending Verification stage)
            task = Task(
                task_type='ENTER_RESULT',
                request_id=req.id,
                assigned_role='LAB_STAFF',
                created_time=now,
                status='PENDING',
                remarks=remarks
            )
            db.session.add(task)
            
        elif new_status == 'Pending Verification':
            # Create a verification task for verifier
            task = Task(
                task_type='VERIFY',
                request_id=req.id,
                assigned_role='VERIFIER',
                created_time=now,
                status='PENDING',
                remarks=remarks
            )
            db.session.add(task)
            
        elif new_status == 'Correction Required':
            # Send back to lab staff for result re-entry
            task = Task(
                task_type='ENTER_RESULT',
                request_id=req.id,
                assigned_role='LAB_STAFF',
                created_time=now,
                status='PENDING',
                remarks=f"Correction requested by {user.name}: {remarks}"
            )
            db.session.add(task)
            
        elif new_status == 'Verified':
            task = Task(
                task_type='DELIVER',
                request_id=req.id,
                assigned_role='BRANCH_STAFF',
                created_time=now,
                status='PENDING',
                remarks=remarks
            )
            db.session.add(task)

    @staticmethod
    def _send_notifications(req, old_status, new_status, user, extra_data):
        """
        Dispatches targeted role or user notifications when status changes.
        """
        priority_notif = 'Emergency' if req.priority == 'Emergency' else 'Routine'
        
        if new_status == 'Pickup Requested':
            msg = f"New sample pickup request! Branch: {req.branch.name}. Priority: {req.priority}."
            NotificationService.send_notification(msg, request_id=req.id, role='SUPERVISOR', priority=priority_notif)
            NotificationService.send_notification(msg, request_id=req.id, role='MANAGER', priority=priority_notif)
            NotificationService.send_notification(msg, request_id=req.id, role='RIDER', priority=priority_notif)
            
        elif new_status == 'Rider Assigned':
            rider_id = extra_data.get('rider_id')
            rider = User.query.get(rider_id)
            method = extra_data.get('method', 'Lab Assigned')
            
            # Notify rider
            rider_msg = f"New pickup task assigned. Branch: {req.branch.name}. Priority: {req.priority}. (Method: {method})"
            NotificationService.send_notification(rider_msg, request_id=req.id, user_id=rider_id, priority=priority_notif)
            
            # Notify branch staff
            branch_msg = f"Rider {rider.name} has been assigned to collect your samples."
            NotificationService.send_notification(branch_msg, request_id=req.id, role='BRANCH_STAFF')
            
        elif new_status == 'Sample Collected':
            msg = f"Sample {req.id} collected from {req.branch.name} by Rider {user.name}."
            NotificationService.send_notification(msg, request_id=req.id, role='SUPERVISOR')
            NotificationService.send_notification(msg, request_id=req.id, role='LAB_STAFF')
            
        elif new_status == 'Arrived at G-8':
            msg = f"Rider {user.name} has arrived at G-8 with sample {req.id}. Ready for receiving."
            NotificationService.send_notification(msg, request_id=req.id, role='LAB_STAFF', priority='Emergency')
            NotificationService.send_notification(msg, request_id=req.id, role='SUPERVISOR')
            
        elif new_status == 'Received at G-8':
            msg = f"Sample {req.id} received at G-8 Main Lab by {user.name}."
            # Notify branch staff
            NotificationService.send_notification(msg, request_id=req.id, role='BRANCH_STAFF')
            NotificationService.send_notification(msg, request_id=req.id, role='SUPERVISOR')
            
        elif new_status == 'Processing Completed':
            msg = f"Processing completed for sample {req.id}. Results pending entry."
            NotificationService.send_notification(msg, request_id=req.id, role='LAB_STAFF')
            
        elif new_status == 'Pending Verification':
            msg = f"Results entered for sample {req.id}. Pending verification."
            NotificationService.send_notification(msg, request_id=req.id, role='VERIFIER', priority=priority_notif)
            
        elif new_status == 'Correction Required':
            # Use remarks parameter directly (history not yet committed at this point)
            msg = f"Results rejected for {req.id}. Correction required: {remarks or 'See details'}"
            NotificationService.send_notification(msg, request_id=req.id, role='LAB_STAFF', priority='Emergency')
            
        elif new_status == 'Verified':
            msg = f"Report verified and ready for delivery for sample {req.id} (Patient: {req.patient_name})."
            # Notify branch
            NotificationService.send_notification(msg, request_id=req.id, role='BRANCH_STAFF')
            
        elif new_status == 'Completed':
            msg = f"Sample {req.id} workflow completed. Report delivered."
            NotificationService.send_notification(msg, request_id=req.id, role='MANAGER')
