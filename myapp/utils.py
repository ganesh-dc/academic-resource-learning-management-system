from .models import Notification
from django.contrib.auth.models import User

def create_notification(receiver, message, notification_type='system', sender=None, resource=None):
    """Utility function to create notifications"""
    notification = Notification.objects.create(
        receiver=receiver,
        sender=sender,
        notification_type=notification_type,
        message=message,
        resource=resource,
        is_read=False
    )
    return notification

def notify_resource_download(resource, downloader):
    """Create notification when resource is downloaded"""
    if resource.uploaded_by != downloader:
        message = f"{downloader.username} downloaded your resource: {resource.title}"
        create_notification(
            receiver=resource.uploaded_by,
            sender=downloader,
            notification_type='download',
            message=message,
            resource=resource
        )

def notify_resource_purchase(resource, buyer):
    """Create notification when premium resource is purchased"""
    message = f"{buyer.username} purchased your premium resource: {resource.title}"
    create_notification(
        receiver=resource.uploaded_by,
        sender=buyer,
        notification_type='purchase',
        message=message,
        resource=resource
    )