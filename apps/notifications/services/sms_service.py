import logging
from typing import Optional

from django.conf import settings

from apps.core.utils import PhoneNumberUtils
from apps.notifications.models import (
    Notification,
    NotificationType,
    SMSNotification,
)
from apps.notifications.providers import BaseSMSProvider, SMSDeliveryResult, get_sms_provider

logger = logging.getLogger("apps.notifications.services.sms_service")


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
        sender_id: Optional[str] = None,
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
        active_sender = sender_id or getattr(settings, "SMS_SENDER_ID", "PindoTest")

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
