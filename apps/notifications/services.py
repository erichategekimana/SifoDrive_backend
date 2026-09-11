"""
apps/notifications/services.py
==============================
Enterprise Notification & SMS Dispatch Service Architecture for Sifo Drive.
Handles template resolution, multi-channel routing (In-App, SMS, Email),
user preferences checking, and asynchronous background worker hand-offs.
"""

from datetime import datetime
import logging
from typing import Any, Dict, List, Optional, Tuple, Union

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.core.utils import PhoneNumberUtils
from apps.notifications.models import (
    Notification,
    NotificationChannel,
    NotificationPreference,
    NotificationPriority,
    NotificationStatus,
    NotificationTemplate,
    NotificationType,
    SMSNotification,
)
from apps.notifications.providers import BaseSMSProvider, SMSDeliveryResult, get_sms_provider

logger = logging.getLogger("apps.notifications.services")


# ---------------------------------------------------------------------------
# Default Built-In Templates (Bilingual: Kinyarwanda & English)
# ---------------------------------------------------------------------------

DEFAULT_TEMPLATES: Dict[Tuple[str, str, str], Dict[str, str]] = {
    # (Type, Language, Channel) -> {"title": ..., "body": ...}
    (NotificationType.OTP, "rw", NotificationChannel.SMS): {
        "title": "Kode yo kwemeza",
        "body": "[Sifo Drive] {purpose_label}: {otp_code}. Birangira mu minota {expiry_minutes}. Ntuzasangize iyi kode undi muntu.",
    },
    (NotificationType.OTP, "en", NotificationChannel.SMS): {
        "title": "Verification Code",
        "body": "[Sifo Drive] {purpose_label}: {otp_code}. Valid for {expiry_minutes} minutes. Do not share this code with anyone.",
    },
    (NotificationType.WELCOME, "rw", NotificationChannel.IN_APP): {
        "title": "Murakaza neza muri Sifo Drive!",
        "body": "Muraho {name}, murakaza neza muri Sifo Drive. Tangira kwiga amategeko y'umuhanda no kwitegura ikizamini cya provisoire.",
    },
    (NotificationType.WELCOME, "en", NotificationChannel.IN_APP): {
        "title": "Welcome to Sifo Drive!",
        "body": "Hello {name}, welcome to Sifo Drive. Start learning traffic regulations and preparing for your provisional driving exam.",
    },
    (NotificationType.GUEST_UPGRADE, "rw", NotificationChannel.IN_APP): {
        "title": "Konti yahinduwe Umunyeshuri",
        "body": "Ubu ufite uburenganzira busesuye ku masomo yose, ibizamini byo kwimenyereza, ndetse na serivisi ya Irembo.",
    },
    (NotificationType.GUEST_UPGRADE, "en", NotificationChannel.IN_APP): {
        "title": "Upgraded to Student Account",
        "body": "You now have full access to all curriculum modules, unlimited mock exams, and Irembo test booking concierge.",
    },
    (NotificationType.PAYMENT_SUCCESS, "rw", NotificationChannel.SMS): {
        "title": "Ubwishyu bwakiriwe",
        "body": "[Sifo Drive] Kwishyura {amount_rwf} RWF byakiriwe neza. Nimero y'ubwishyu: {transaction_ref}. Murakoze!",
    },
    (NotificationType.PAYMENT_SUCCESS, "en", NotificationChannel.SMS): {
        "title": "Payment Confirmed",
        "body": "[Sifo Drive] Payment of {amount_rwf} RWF received successfully. Ref: {transaction_ref}. Thank you!",
    },
    (NotificationType.PAYMENT_FAILED, "rw", NotificationChannel.SMS): {
        "title": "Kwishyura ntibikunze",
        "body": "[Sifo Drive] Kwishyura {amount_rwf} RWF ntibikunze. Ongera ugerageze cyangwa urebe niba ufite amafaranga ahagije.",
    },
    (NotificationType.PAYMENT_FAILED, "en", NotificationChannel.SMS): {
        "title": "Payment Failed",
        "body": "[Sifo Drive] Payment of {amount_rwf} RWF could not be completed. Please check your mobile money balance and retry.",
    },
    (NotificationType.BOOKING_QUEUED, "rw", NotificationChannel.SMS): {
        "title": "Gusaba Irembo byakiriwe",
        "body": "[Sifo Drive] Gusaba gushakirwa umwanya w'ikizamini cy'amategeko byakiriwe. Nimero yo gukurikirana: {application_number}.",
    },
    (NotificationType.BOOKING_QUEUED, "en", NotificationChannel.SMS): {
        "title": "Irembo Booking Queued",
        "body": "[Sifo Drive] Your provisional driving test booking request is queued. Tracking Ref: {application_number}.",
    },
    (NotificationType.BOOKING_CONFIRMED, "rw", NotificationChannel.SMS): {
        "title": "Umwanya w'ikizamini wemejwe",
        "body": "[Sifo Drive] Umwanya w'ikizamini cyawe wemejwe! Itariki: {test_date}, Ikigo: {test_center}. Nimero ya Irembo: {irembo_ref}.",
    },
    (NotificationType.BOOKING_CONFIRMED, "en", NotificationChannel.SMS): {
        "title": "Driving Test Slot Confirmed",
        "body": "[Sifo Drive] Your exam slot is confirmed! Date: {test_date}, Center: {test_center}. Irembo Ref: {irembo_ref}.",
    },
    (NotificationType.BOOKING_SLOTS_EXHAUSTED, "rw", NotificationChannel.SMS): {
        "title": "Imyanya yuzuye",
        "body": "[Sifo Drive] Imyanya y'ikizamini muri aka kanya yarangiye. Urakomeza kuba ku rutonde, tuzakumenyesha imyanya ifungutse.",
    },
    (NotificationType.BOOKING_SLOTS_EXHAUSTED, "en", NotificationChannel.SMS): {
        "title": "Slots Currently Exhausted",
        "body": "[Sifo Drive] Current test slots are filled. You remain in queue and will be notified as soon as new slots open.",
    },
    (NotificationType.BOOKING_REMINDER, "rw", NotificationChannel.SMS): {
        "title": "Ubwibutso bw'ikizamini",
        "body": "[Sifo Drive] Ubwibutso: Ikizamini cyawe kizaba {test_date} kuri {test_center}. Witwaze indangamuntu yawe.",
    },
    (NotificationType.BOOKING_REMINDER, "en", NotificationChannel.SMS): {
        "title": "Exam Reminder",
        "body": "[Sifo Drive] Reminder: Your physical test is on {test_date} at {test_center}. Bring your original National ID card.",
    },
    (NotificationType.EXAM_RESULT, "rw", NotificationChannel.IN_APP): {
        "title": "Ibisubizo by'ikizamini cyo kwimenyereza",
        "body": "Watsinze amanota {score}/{max_score} ({result_status}). Reba aho wakoze amakosa muri raporo y'ikizamini.",
    },
    (NotificationType.EXAM_RESULT, "en", NotificationChannel.IN_APP): {
        "title": "Practice Exam Result",
        "body": "You scored {score}/{max_score} ({result_status}). Review correct explanations on your test report.",
    },
    (NotificationType.LIVE_CLASS_SCHEDULED, "rw", NotificationChannel.IN_APP): {
        "title": "Isomo ry'imbona-nkubone rirateganyijwe",
        "body": "Isomo '{title}' rirateganyijwe kuwa {class_time}. Umwarimu: {tutor_name}.",
    },
    (NotificationType.LIVE_CLASS_SCHEDULED, "en", NotificationChannel.IN_APP): {
        "title": "Live Class Scheduled",
        "body": "Live lesson '{title}' is scheduled for {class_time}. Tutor: {tutor_name}.",
    },
    (NotificationType.LIVE_CLASS_REMINDER, "rw", NotificationChannel.SMS): {
        "title": "Isomo ritangiye",
        "body": "[Sifo Drive] Isomo ryawe ritangira mu minota 15! Fungura link y'isomo: {meet_link}",
    },
    (NotificationType.LIVE_CLASS_REMINDER, "en", NotificationChannel.SMS): {
        "title": "Live Class Starting Soon",
        "body": "[Sifo Drive] Your live class starts in 15 minutes! Join here: {meet_link}",
    },
}


# ---------------------------------------------------------------------------
# Template Service
# ---------------------------------------------------------------------------

class TemplateService:
    """
    Renders message templates with graceful fallback to hardcoded bilingual defaults.
    Ensures message dispatch never crashes even if a database template is absent.
    """

    @classmethod
    def render(
        cls,
        notification_type: str,
        channel: str,
        language: str = "rw",
        context: Optional[Dict[str, Any]] = None,
        template_code: Optional[str] = None,
    ) -> Tuple[str, str]:
        """
        Render title and body for given notification type and channel.

        Returns:
            Tuple of (rendered_title, rendered_body)
        """
        ctx = context or {}
        lang = language if language in ("rw", "en", "fr") else "rw"

        # 1. Attempt lookup from DB template
        try:
            if template_code:
                db_template = NotificationTemplate.objects.filter(
                    template_code=template_code,
                    is_active=True,
                ).first()
            else:
                db_template = NotificationTemplate.objects.filter(
                    notification_type=notification_type,
                    channel=channel,
                    language=lang,
                    is_active=True,
                ).first()

            if db_template:
                return db_template.render(ctx)
        except Exception as exc:
            logger.warning("Failed to fetch template from DB: %s. Using default.", exc)

        # 2. Fallback to hardcoded bilingual template
        fallback = DEFAULT_TEMPLATES.get((notification_type, lang, channel))
        if not fallback and lang != "en":
            # Fallback to English if Kinyarwanda not found
            fallback = DEFAULT_TEMPLATES.get((notification_type, "en", channel))
        if not fallback:
            # Fallback across channels (e.g. IN_APP template for SMS body)
            for ch in (NotificationChannel.SMS, NotificationChannel.IN_APP):
                fallback = DEFAULT_TEMPLATES.get((notification_type, lang, ch))
                if fallback:
                    break

        if fallback:
            class SafeDict(dict):
                def __missing__(self, key):
                    return f"{{{key}}}"

            safe_ctx = SafeDict(ctx)
            title = fallback.get("title", "").format_map(safe_ctx)
            body = fallback.get("body", "").format_map(safe_ctx)
            return title, body

        # 3. Absolute generic fallback
        generic_title = ctx.get("title", f"Sifo Drive: {notification_type.replace('_', ' ').title()}")
        generic_body = ctx.get("body", f"[Sifo Drive Notification - {notification_type}]")
        return generic_title, generic_body


# ---------------------------------------------------------------------------
# SMS Dispatcher Service
# ---------------------------------------------------------------------------

class SMSDispatcherService:
    """
    Direct SMS sending, normalization, audit logging, and provider error containment.
    """

    @classmethod
    def send_sms(
        cls,
        phone_number: str,
        message: str,
        message_type: str = NotificationType.GENERAL,
        sender_id: str = "SIFO_DRIVE",
        parent_notification: Optional[Notification] = None,
        provider_name: Optional[str] = None,
    ) -> SMSDeliveryResult:
        """
        Normalize phone number and dispatch SMS via configured gateway.
        Logs every attempt to the SMSNotification table.
        """
        normalized_phone = PhoneNumberUtils.normalize(phone_number, default_region="RW")
        if not normalized_phone:
            logger.error("SMS dispatch aborted: invalid phone number '%s'", phone_number)
            return SMSDeliveryResult(
                success=False,
                status="FAILED",
                error_message=f"Invalid phone number for Rwanda: {phone_number}",
            )

        provider: BaseSMSProvider = get_sms_provider(provider_name)
        active_sender = sender_id or getattr(settings, "SMS_SENDER_ID", "SIFO_DRIVE")

        # 1. Create PENDING audit log record
        sms_log = SMSNotification.objects.create(
            notification=parent_notification,
            recipient_phone=normalized_phone,
            message_type=message_type,
            message_body=message,
            sender_id=active_sender,
            provider=provider.get_provider_name(),
            status="PENDING",
        )

        # 2. Dispatch through provider
        try:
            result = provider.send_sms(
                recipient=normalized_phone,
                message=message,
                sender_id=active_sender,
            )

            if result.success:
                sms_log.mark_sent(result.message_id or "", result.raw_response)
                logger.info(
                    "SMS sent successfully | to=…%s type=%s provider=%s id=%s",
                    normalized_phone[-4:],
                    message_type,
                    provider.get_provider_name(),
                    result.message_id,
                )
            else:
                sms_log.mark_failed(result.error_message or "Provider rejected message", result.raw_response)
                logger.warning(
                    "SMS delivery failed | to=…%s type=%s provider=%s error=%s",
                    normalized_phone[-4:],
                    message_type,
                    provider.get_provider_name(),
                    result.error_message,
                )
            return result

        except Exception as exc:
            logger.error(
                "Unexpected exception during SMS dispatch | to=…%s error=%s",
                normalized_phone[-4:],
                exc,
                exc_info=True,
            )
            sms_log.mark_failed(str(exc))
            return SMSDeliveryResult(
                success=False,
                status="FAILED",
                error_message=str(exc),
            )


# ---------------------------------------------------------------------------
# Notification Service (High-Level Orchestrator)
# ---------------------------------------------------------------------------

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
