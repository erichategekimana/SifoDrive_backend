import logging
from typing import Any, Dict, Optional, Tuple

from apps.notifications.models import (
    NotificationChannel,
    NotificationTemplate,
    NotificationType,
)

logger = logging.getLogger("apps.notifications.services.template_service")

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
