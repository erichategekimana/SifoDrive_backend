"""
apps/notifications/providers/console.py
=======================================
Console/Mock SMS provider for local development, CI pipelines, and unit tests.
Outputs formatted SMS message blocks to Python logging and returns simulated success.
"""

import logging
import uuid
from apps.notifications.providers.base import BaseSMSProvider, SMSDeliveryResult

logger = logging.getLogger("apps.notifications.sms.console")


class ConsoleSMSProvider(BaseSMSProvider):
    """Logs SMS content directly to console/logger without external network calls."""

    def get_provider_name(self) -> str:
        return "CONSOLE_MOCK"

    def send_sms(
        self,
        recipient: str,
        message: str,
        sender_id: str = "SIFO_DRIVE",
    ) -> SMSDeliveryResult:
        simulated_id = f"mock-sms-{uuid.uuid4().hex[:12]}"
        
        logger.info(
            "\n"
            "┌──────────────────────────────────────────────────────────\n"
            "│ 📱 [CONSOLE SMS DISPATCH]\n"
            "│ From:      %s\n"
            "│ To:        %s\n"
            "│ ID:        %s\n"
            "│ Body:      %s\n"
            "└──────────────────────────────────────────────────────────",
            sender_id,
            recipient,
            simulated_id,
            message,
        )

        return SMSDeliveryResult(
            success=True,
            message_id=simulated_id,
            status="SENT",
            raw_response={
                "provider": "console",
                "recipient": recipient,
                "sender_id": sender_id,
                "message": message,
            },
        )
