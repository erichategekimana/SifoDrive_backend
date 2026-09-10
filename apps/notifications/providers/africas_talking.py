"""
apps/notifications/providers/africas_talking.py
===============================================
Africa's Talking SMS Gateway integration.
Supports regional dispatch across East Africa including Rwanda (+250).
"""

import logging
from typing import Optional
import requests
from django.conf import settings

from apps.notifications.providers.base import BaseSMSProvider, SMSDeliveryResult

logger = logging.getLogger("apps.notifications.sms.africas_talking")


class AfricasTalkingSMSProvider(BaseSMSProvider):
    """
    Client for Africa's Talking messaging API.
    Doc: https://developers.africastalking.com/docs/sms/sending
    """

    LIVE_URL = "https://api.africastalking.com/version1/messaging"
    SANDBOX_URL = "https://api.sandbox.africastalking.com/version1/messaging"

    def __init__(
        self,
        username: Optional[str] = None,
        api_key: Optional[str] = None,
        is_sandbox: bool = False,
    ):
        self.username = username or getattr(settings, "AFRICAS_TALKING_USERNAME", "")
        self.api_key = api_key or getattr(settings, "AFRICAS_TALKING_API_KEY", "")
        self.is_sandbox = is_sandbox or (self.username.lower() == "sandbox")
        self.url = self.SANDBOX_URL if self.is_sandbox else self.LIVE_URL

    def get_provider_name(self) -> str:
        return "AFRICAS_TALKING"

    def send_sms(
        self,
        recipient: str,
        message: str,
        sender_id: str = "SIFO_DRIVE",
    ) -> SMSDeliveryResult:
        if not self.username or not self.api_key:
            logger.error("Africa's Talking credentials not configured in settings")
            return SMSDeliveryResult(
                success=False,
                error_message="AFRICAS_TALKING credentials not configured",
                status="FAILED",
            )

        headers = {
            "apiKey": self.api_key,
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {
            "username": self.username,
            "to": recipient,
            "message": message,
        }
        if sender_id and not self.is_sandbox:
            data["from"] = sender_id

        try:
            response = requests.post(
                self.url,
                data=data,
                headers=headers,
                timeout=10.0,
            )
            raw_data = response.json() if response.content else {}

            if response.status_code in (200, 201):
                recipients = (
                    raw_data.get("SMSMessageData", {}).get("Recipients", [])
                )
                if recipients:
                    first = recipients[0]
                    status = first.get("status", "")
                    msg_id = first.get("messageId", "")
                    is_success = status.lower() in ("success", "sent")
                    return SMSDeliveryResult(
                        success=is_success,
                        message_id=msg_id,
                        status="SENT" if is_success else "FAILED",
                        raw_response=raw_data,
                        error_message=None if is_success else f"Status: {status}",
                    )
                return SMSDeliveryResult(
                    success=True,
                    status="SENT",
                    raw_response=raw_data,
                )
            else:
                logger.warning(
                    "Africa's Talking dispatch rejected | status=%s to=…%s",
                    response.status_code,
                    recipient[-4:],
                )
                return SMSDeliveryResult(
                    success=False,
                    status="FAILED",
                    raw_response=raw_data,
                    error_message=f"HTTP {response.status_code}: {response.text}",
                )
        except requests.RequestException as exc:
            logger.error("Africa's Talking network error | to=…%s error=%s", recipient[-4:], exc)
            return SMSDeliveryResult(
                success=False,
                status="FAILED",
                error_message=str(exc),
            )
