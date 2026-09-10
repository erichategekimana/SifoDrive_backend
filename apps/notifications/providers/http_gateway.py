"""
apps/notifications/providers/http_gateway.py
============================================
Generic HTTP webhook / REST SMS gateway provider.
Works with any custom provider implementing a standard JSON POST contract.
"""

import logging
from typing import Optional
import requests
from django.conf import settings

from apps.notifications.providers.base import BaseSMSProvider, SMSDeliveryResult

logger = logging.getLogger("apps.notifications.sms.http")


class HttpGatewaySMSProvider(BaseSMSProvider):
    """Dispatches SMS to any arbitrary configured gateway URL."""

    def __init__(
        self,
        gateway_url: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        self.gateway_url = gateway_url or getattr(settings, "SMS_GATEWAY_URL", "")
        self.api_key = api_key or getattr(settings, "SMS_API_KEY", "")

    def get_provider_name(self) -> str:
        return "HTTP_GATEWAY"

    def send_sms(
        self,
        recipient: str,
        message: str,
        sender_id: str = "SIFO_DRIVE",
    ) -> SMSDeliveryResult:
        if not self.gateway_url:
            logger.error("SMS_GATEWAY_URL not configured in settings")
            return SMSDeliveryResult(
                success=False,
                error_message="SMS_GATEWAY_URL not configured",
                status="FAILED",
            )

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "to": recipient,
            "recipient": recipient,
            "from": sender_id,
            "sender_id": sender_id,
            "message": message,
            "text": message,
        }

        try:
            response = requests.post(
                self.gateway_url,
                json=payload,
                headers=headers,
                timeout=10.0,
            )
            raw_data = response.json() if response.content else {}

            if response.status_code in (200, 201, 202):
                msg_id = (
                    str(raw_data.get("message_id"))
                    or str(raw_data.get("id"))
                    or str(raw_data.get("tracking_id"))
                    or ""
                )
                return SMSDeliveryResult(
                    success=True,
                    message_id=msg_id,
                    status="SENT",
                    raw_response=raw_data,
                )
            else:
                return SMSDeliveryResult(
                    success=False,
                    status="FAILED",
                    raw_response=raw_data,
                    error_message=f"HTTP {response.status_code}: {response.text}",
                )
        except requests.RequestException as exc:
            logger.error("HTTP SMS gateway error | to=…%s error=%s", recipient[-4:], exc)
            return SMSDeliveryResult(
                success=False,
                status="FAILED",
                error_message=str(exc),
            )
