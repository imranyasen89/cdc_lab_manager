from app.utils.timezone import now_pkt
from app.models import TATRule

class TATService:
    @staticmethod
    def get_stage_durations(request):
        """
        Calculates the active duration for each workflow stage in minutes
        using the timestamps recorded in the status history logs.
        """
        history = {h.status: h.timestamp for h in request.history}
        created_at = request.created_at
        
        assigned_at = history.get('Rider Assigned')
        collected_at = history.get('Sample Collected')
        arrived_g8_at = history.get('Arrived at G-8')
        received_g8_at = history.get('Received at G-8')
        processing_start = history.get('Processing')
        processing_end = history.get('Processing Completed')
        result_entered = history.get('Pending Verification')
        verified_at = history.get('Verified')
        delivered_at = history.get('Completed')
        
        def diff_minutes(t1, t2):
            if not t1 or not t2:
                return None
            return round((t2 - t1).total_seconds() / 60.0, 1)
            
        return {
            'pickup_response': diff_minutes(created_at, assigned_at),
            'rider_response': diff_minutes(created_at, assigned_at),  # Assignment / acceptance time
            'branch_pickup': diff_minutes(created_at, collected_at),
            'transport': diff_minutes(collected_at, received_g8_at),
            'receiving_delay': diff_minutes(arrived_g8_at, received_g8_at),
            'processing': diff_minutes(processing_start, processing_end),
            'verification': diff_minutes(result_entered, verified_at),
            'delivery': diff_minutes(verified_at, delivered_at),
            'total_tat': diff_minutes(created_at, delivered_at or now_pkt())
        }
        
    @staticmethod
    def check_is_delayed(request):
        """
        Checks if a sample request has exceeded its configured TAT rule limit.
        If it's completed, compare total_tat against max_tat.
        If it's active, compare elapsed time since creation against max_tat.
        """
        rule = TATRule.query.filter_by(priority=request.priority).first()
        if not rule:
            return False, 0.0, 0.0
            
        durations = TATService.get_stage_durations(request)
        total_elapsed = durations['total_tat'] or 0.0
        max_limit = float(rule.max_tat_minutes)
        
        is_delayed = total_elapsed > max_limit
        return is_delayed, total_elapsed, max_limit
