"""
apps/notifications/tasks.py
===========================
Asynchronous Celery background workers for SMS dispatch and batch notifications.
Includes automatic retries with exponential backoff for transient telecom gateway failures.
"""

import logging
from typing import List, Optional
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger("apps.notifications.tasks")


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
    name="notifications.send_otp_sms",
)
def send_otp_sms_task(self, phone_number: str, raw_otp: str, purpose: str = "REGISTRATION"):
    """
    High-priority async task to dispatch an OTP SMS.
    Maintains 100% backward compatibility with apps.accounts.services.AuthService.
    """
    from apps.notifications.services import NotificationService
    try:
        NotificationService.send_otp(
            phone_number=phone_number,
            raw_otp=raw_otp,
            purpose=purpose,
            language="rw",
        )
        logger.info("OTP SMS dispatched successfully | phone=…%s purpose=%s", phone_number[-4:], purpose)
    except Exception as exc:
        logger.error("OTP SMS task failed | phone=…%s error=%s", phone_number[-4:], exc)
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
    name="notifications.dispatch_sms",
)
def dispatch_sms_task(
    self,
    phone_number: str,
    message: str,
    message_type: str = "GENERAL",
    notification_id: Optional[str] = None,
):
    """
    Generic background task to send an SMS and update the parent Notification record.
    """
    from apps.notifications.models import Notification, NotificationStatus
    from apps.notifications.services import SMSDispatcherService

    parent_notif = None
    if notification_id:
        try:
            parent_notif = Notification.objects.filter(id=notification_id).first()
        except Exception:
            pass

    result = SMSDispatcherService.send_sms(
        phone_number=phone_number,
        message=message,
        message_type=message_type,
        parent_notification=parent_notif,
    )

    if parent_notif:
        if result.success:
            parent_notif.status = NotificationStatus.SENT
            parent_notif.sent_at = timezone.now()
        else:
            parent_notif.status = NotificationStatus.FAILED
        parent_notif.save(update_fields=["status", "sent_at", "updated_at"])

    if not result.success:
        logger.warning("dispatch_sms_task provider reported failure | phone=…%s", phone_number[-4:])


@shared_task(name="notifications.send_bulk_notification")
def send_bulk_notification_task(
    recipient_ids: List[str],
    title: str,
    body: str,
    title_rw: str = "",
    body_rw: str = "",
    channel: str = "IN_APP",
    priority: str = "NORMAL",
    action_url: str = "",
):
    """
    Background worker to create mass notifications in chunks of 500.
    Prevents database lockups during platform-wide announcements.
    """
    from apps.accounts.models import User
    from apps.notifications.models import Notification, NotificationStatus

    batch_size = 500
    now = timezone.now()

    for i in range(0, len(recipient_ids), batch_size):
        chunk_ids = recipient_ids[i:i + batch_size]
        users = User.objects.filter(id__in=chunk_ids)

        notifications_to_create = [
            Notification(
                recipient=user,
                recipient_phone=user.phone_number,
                recipient_email=user.email or "",
                notification_type="SYSTEM_ANNOUNCEMENT",
                channel=channel,
                priority=priority,
                title=title,
                title_rw=title_rw or title,
                body=body,
                body_rw=body_rw or body,
                action_url=action_url,
                status=NotificationStatus.DELIVERED if channel == "IN_APP" else NotificationStatus.PENDING,
                sent_at=now,
            )
            for user in users
        ]
        Notification.objects.bulk_create(notifications_to_create)
        logger.info("Created batch of %d broadcast notifications", len(notifications_to_create))


@shared_task(name="notifications.cleanup_old_sms_logs")
def cleanup_old_sms_logs_task(days: int = 180):
    """
    Compliance maintenance: prune SMS transmission records older than retention period.
    """
    from datetime import timedelta
    from apps.notifications.models import SMSNotification

    cutoff = timezone.now() - timedelta(days=days)
    deleted_count, _ = SMSNotification.objects.filter(created_at__lt=cutoff).delete()
    logger.info("Purged %d old SMS notification logs older than %d days", deleted_count, days)
    return deleted_count
