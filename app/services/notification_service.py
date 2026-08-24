from app import db
from app.models import Notification

class NotificationService:
    @staticmethod
    def send_notification(message, request_id=None, user_id=None, role=None, priority='Routine'):
        """
        Creates and stores an in-app notification.
        This serves as an extensible hub where future external integrations
        (SMS, WhatsApp, email, push) can be easily integrated.
        """
        notif = Notification(
            message=message,
            request_id=request_id,
            user_id=user_id,
            assigned_role=role,
            priority=priority
        )
        db.session.add(notif)
        
        # Extensible hooks:
        # if role == 'RIDER':
        #     # Trigger mobile push notification / WhatsApp dispatch
        #     pass
        
        return notif
