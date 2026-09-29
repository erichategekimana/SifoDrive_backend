import logging
from typing import Any, Dict, Optional, Union

from django.conf import settings
from django.utils import timezone

from apps.accounts.models import User
from apps.notifications.models import (
    Notification,
    NotificationChannel,
    NotificationPreference,
    NotificationPriority,
    NotificationStatus,
    NotificationType,
)
from .template_service import TemplateService
from .sms_service import SMSDispatcherService

logger = logging.getLogger("apps.notifications.services.notification_service")


class NotificationService:
    """
    Main entry point for dispatching notifications across all platform apps.
    Manages in-app feed creation, preference verification, and background worker queueing.
    """

    @classmethod
    def send_notification(
        cls,
        notification_type: str,
        recipient: Optional[User] = None,
        recipient_phone: Optional[str] = None,
        recipient_email: Optional[str] = None,
        channel: str = NotificationChannel.IN_APP,
        priority: str = NotificationPriority.NORMAL,
        context: Optional[Dict[str, Any]] = None,
        action_url: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        language: Optional[str] = None,
    ) -> Notification:
        """
        Create and dispatch a notification.
        If recipient has preferences configured, respects opt-in / opt-out flags.
        """
        ctx = context or {}
        meta = metadata or {}

        # Resolve destination attributes
        phone = recipient_phone or (recipient.phone_number if (recipient and recipient.phone_number) else "")
        email = recipient_email or (recipient.email if (recipient and recipient.email) else "")

        # Resolve user preference and language
        lang = language
        if recipient and not lang:
            try:
                prefs = recipient.notification_preferences
                lang = prefs.preferred_language
                # Respect channel preferences
                if channel == NotificationChannel.SMS and not prefs.sms_enabled:
                    logger.info("SMS notification skipped due to user preference | user=%s", recipient.id)
                    channel = NotificationChannel.IN_APP
                elif channel == NotificationChannel.EMAIL and not prefs.email_enabled:
                    channel = NotificationChannel.IN_APP
            except (NotificationPreference.DoesNotExist, AttributeError):
                lang = "rw"
        lang = lang or "rw"

        # Render content for both languages where applicable
        title_en, body_en = TemplateService.render(
            notification_type=notification_type,
            channel=channel,
            language="en",
            context=ctx,
        )
        title_rw, body_rw = TemplateService.render(
            notification_type=notification_type,
            channel=channel,
            language="rw",
            context=ctx,
        )

        title = title_rw if lang == "rw" else title_en
        body = body_rw if lang == "rw" else body_en

        # 1. Create In-App Notification Record
        notification = Notification.objects.create(
            recipient=recipient,
            recipient_phone=phone,
            recipient_email=email,
            notification_type=notification_type,
            channel=channel,
            priority=priority,
            title=title_en,
            title_rw=title_rw,
            body=body_en,
            body_rw=body_rw,
            action_url=action_url,
            metadata=meta,
            status=NotificationStatus.PENDING,
        )

        # 2. Dispatch or Queue based on channel
        if channel == NotificationChannel.SMS and phone:
            cls._queue_or_send_sms(
                phone_number=phone,
                message=body,
                message_type=notification_type,
                notification=notification,
            )
        else:
            # In-App is immediately available to the user
            notification.status = NotificationStatus.DELIVERED
            notification.sent_at = timezone.now()
            notification.save(update_fields=["status", "sent_at", "updated_at"])

        return notification

    @classmethod
    def _queue_or_send_sms(
        cls,
        phone_number: str,
        message: str,
        message_type: str,
        notification: Optional[Notification] = None,
    ) -> None:
        """Hand off SMS to Celery worker or send synchronously in eager mode."""
        from apps.notifications.tasks import dispatch_sms_task

        if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
            # Run synchronously
            SMSDispatcherService.send_sms(
                phone_number=phone_number,
                message=message,
                message_type=message_type,
                parent_notification=notification,
            )
            if notification:
                notification.status = NotificationStatus.SENT
                notification.sent_at = timezone.now()
                notification.save(update_fields=["status", "sent_at", "updated_at"])
        else:
            # Queue to Celery
            dispatch_sms_task.delay(
                phone_number=phone_number,
                message=message,
                message_type=message_type,
                notification_id=str(notification.id) if notification else None,
            )
            if notification:
                notification.status = NotificationStatus.QUEUED
                notification.save(update_fields=["status", "updated_at"])

    # ──────────────────────────────────────────────────────────────────────────
    # Domain Convenience Methods
    # ──────────────────────────────────────────────────────────────────────────

    @classmethod
    def send_otp(
        cls,
        phone_number: str,
        raw_otp: str,
        purpose: str = "REGISTRATION",
        language: str = "rw",
    ) -> None:
        """
        Fast high-priority SMS OTP dispatch.
        Called directly by AuthService.
        """
        purpose_labels_rw = {
            "REGISTRATION": "Kwemeza konti yawe",
            "LOGIN": "Kwinjira muri konti",
            "PASSWORD_RESET": "Guhindura ijambo ry'ibanga",
            "IREMBO_BOOKING": "Kwemeza gusaba Irembo",
        }
        purpose_labels_en = {
            "REGISTRATION": "Verify your account",
            "LOGIN": "Login verification",
            "PASSWORD_RESET": "Password reset",
            "IREMBO_BOOKING": "Confirm Irembo booking",
        }

        purpose_label = (
            purpose_labels_rw.get(purpose, "Kwemeza")
            if language == "rw"
            else purpose_labels_en.get(purpose, "Verification")
        )

        context = {
            "purpose_label": purpose_label,
            "otp_code": raw_otp,
            "expiry_minutes": getattr(settings, "OTP_EXPIRY_MINUTES", 10),
        }

        _, body = TemplateService.render(
            notification_type=NotificationType.OTP,
            channel=NotificationChannel.SMS,
            language=language,
            context=context,
        )

        cls._queue_or_send_sms(
            phone_number=phone_number,
            message=body,
            message_type=NotificationType.OTP,
        )

    @classmethod
    def send_welcome(cls, user: User, language: str = "rw") -> Notification:
        return cls.send_notification(
            recipient=user,
            notification_type=NotificationType.WELCOME,
            channel=NotificationChannel.IN_APP,
            context={"name": user.get_full_name() or user.phone_number},
            action_url="/dashboard",
            language=language,
        )

    @classmethod
    def send_guest_upgraded(cls, user: User, language: str = "rw") -> Notification:
        # Both In-App and SMS alert
        notif = cls.send_notification(
            recipient=user,
            notification_type=NotificationType.GUEST_UPGRADE,
            channel=NotificationChannel.IN_APP,
            context={"name": user.get_full_name()},
            action_url="/courses",
            language=language,
        )
        if user.phone_number:
            cls.send_notification(
                recipient=user,
                notification_type=NotificationType.GUEST_UPGRADE,
                channel=NotificationChannel.SMS,
                context={"name": user.get_full_name()},
                language=language,
            )
        return notif

    @classmethod
    def send_payment_receipt(
        cls,
        user: User,
        amount_rwf: Union[int, float, str],
        transaction_ref: str,
        language: str = "rw",
    ) -> Notification:
        context = {
            "amount_rwf": f"{int(amount_rwf):,}",
            "transaction_ref": transaction_ref,
        }
        return cls.send_notification(
            recipient=user,
            notification_type=NotificationType.PAYMENT_SUCCESS,
            channel=NotificationChannel.SMS,
            context=context,
            action_url="/payments/receipts",
            metadata={"transaction_ref": transaction_ref, "amount": str(amount_rwf)},
            language=language,
        )

    @classmethod
    def send_irembo_booking_confirmed(
        cls,
        user: User,
        test_date: str,
        test_center: str,
        irembo_ref: str,
        language: str = "rw",
    ) -> Notification:
        context = {
            "test_date": test_date,
            "test_center": test_center,
            "irembo_ref": irembo_ref,
        }
        return cls.send_notification(
            recipient=user,
            notification_type=NotificationType.BOOKING_CONFIRMED,
            channel=NotificationChannel.SMS,
            priority=NotificationPriority.HIGH,
            context=context,
            action_url="/irembo/booking",
            metadata=context,
            language=language,
        )

    @classmethod
    def send_irembo_booking_queued(
        cls,
        user: User,
        application_number: str,
        language: str = "rw",
    ) -> Notification:
        context = {"application_number": application_number}
        return cls.send_notification(
            recipient=user,
            notification_type=NotificationType.BOOKING_QUEUED,
            channel=NotificationChannel.SMS,
            context=context,
            action_url="/irembo/queue",
            metadata=context,
            language=language,
        )

    @classmethod
    def send_exam_result(
        cls,
        user: User,
        score: int,
        max_score: int = 20,
        passed: bool = False,
        exam_id: Optional[str] = None,
        language: str = "rw",
    ) -> Notification:
        result_status = "Watsinze (Passed)" if passed else "Ntiwatsinze (Try Again)"
        context = {
            "score": score,
            "max_score": max_score,
            "result_status": result_status,
        }
        action_url = f"/exams/review/{exam_id}" if exam_id else "/exams"
        return cls.send_notification(
            recipient=user,
            notification_type=NotificationType.EXAM_RESULT,
            channel=NotificationChannel.IN_APP,
            context=context,
            action_url=action_url,
            metadata={"score": score, "passed": passed, "exam_id": str(exam_id) if exam_id else None},
            language=language,
        )

    @classmethod
    def send_live_class_scheduled(
        cls,
        user: User,
        title: str,
        class_time: str,
        tutor_name: str,
        live_class_id: Optional[str] = None,
        language: str = "rw",
    ) -> Notification:
        context = {
            "title": title,
            "class_time": class_time,
            "tutor_name": tutor_name,
        }
        action_url = f"/live-classes/{live_class_id}" if live_class_id else "/live-classes"
        return cls.send_notification(
            recipient=user,
            notification_type=NotificationType.LIVE_CLASS_SCHEDULED,
            channel=NotificationChannel.IN_APP,
            context=context,
            action_url=action_url,
            metadata={"live_class_id": str(live_class_id) if live_class_id else None},
            language=language,
        )

    @classmethod
    def send_live_class_reminder(
        cls,
        user: User,
        meet_link: str,
        live_class_id: Optional[str] = None,
        language: str = "rw",
    ) -> Notification:
        context = {
            "meet_link": meet_link,
        }
        action_url = meet_link
        return cls.send_notification(
            recipient=user,
            notification_type=NotificationType.LIVE_CLASS_REMINDER,
            channel=NotificationChannel.SMS,
            context=context,
            action_url=action_url,
            metadata={"live_class_id": str(live_class_id) if live_class_id else None},
            language=language,
        )

    @classmethod
    def send_broadcast(
        cls,
        title: str,
        body: str,
        title_rw: str = "",
        body_rw: str = "",
        target_role: Optional[str] = None,
        channel: str = NotificationChannel.IN_APP,
        priority: str = NotificationPriority.NORMAL,
        action_url: str = "",
    ) -> int:
        """
        Dispatch mass broadcast announcement to all active users or a specific role segment.
        Returns count of notifications created.
        """
        from apps.notifications.tasks import send_bulk_notification_task

        queryset = User.objects.filter(is_active=True)
        if target_role:
            queryset = queryset.filter(role=target_role)

        recipient_ids = list(queryset.values_list("id", flat=True))
        if not recipient_ids:
            return 0

        send_bulk_notification_task.delay(
            recipient_ids=[str(uid) for uid in recipient_ids],
            title=title,
            body=body,
            title_rw=title_rw,
            body_rw=body_rw,
            channel=channel,
            priority=priority,
            action_url=action_url,
        )
        return len(recipient_ids)

    # ──────────────────────────────────────────────────────────────────────────
    # User Inbox Feed Helpers
    # ──────────────────────────────────────────────────────────────────────────

    @classmethod
    def get_unread_count(cls, user: User) -> int:
        return Notification.objects.filter(recipient=user, is_read=False).count()

    @classmethod
    def mark_as_read(cls, user: User, notification_id: str) -> bool:
        try:
            notif = Notification.objects.get(id=notification_id, recipient=user)
            notif.mark_as_read()
            return True
        except Notification.DoesNotExist:
            return False

    @classmethod
    def mark_all_as_read(cls, user: User) -> int:
        return Notification.objects.mark_all_as_read(user)

    @classmethod
    def get_user_preferences(cls, user: User) -> NotificationPreference:
        prefs, _ = NotificationPreference.objects.get_or_create(user=user)
        return prefs

    @classmethod
    def update_user_preferences(cls, user: User, **kwargs) -> NotificationPreference:
        prefs = cls.get_user_preferences(user)
        allowed_fields = {
            "sms_enabled",
            "in_app_enabled",
            "email_enabled",
            "exam_alerts",
            "booking_alerts",
            "promo_alerts",
            "preferred_language",
        }
        for field, value in kwargs.items():
            if field in allowed_fields:
                setattr(prefs, field, value)
        prefs.save()
        return prefs
