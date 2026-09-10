"""
apps/notifications/providers/pindo.py
=====================================
Pindo SMS gateway integration for Rwanda (https://api.pindo.io).
Supports standard bearer token authentication and synchronous dispatch.
"""

import logging
from typing import Optional
import requests
from django.conf import settings

from apps.notifications.providers.base import BaseSMSProvider, SMSDeliveryResult

logger = logging.getLogger("apps.notifications.sms.pindo")


class PindoSMSProvider(BaseSMSProvider):
    """
    Client for Pindo SMS API (Rwanda local gateway).
    Doc: https://pindo.io/docs
    """

    PINDO_URL = "https://api.pindo.io/v1/sms/"

    def __init__(self, api_token: Optional[str] = None):
        self.api_token = api_token or getattr(settings, "PINDO_API_TOKEN", "")

    def get_provider_name(self) -> str:
        return "PINDO"

    def send_sms(
        self,
        recipient: str,
        message: str,
        sender_id: str = "SIFO_DRIVE",
    ) -> SMSDeliveryResult:
        if not self.api_token:
            logger.error("Pindo API token not configured in settings")
            return SMSDeliveryResult(
                success=False,
                error_message="PINDO_API_TOKEN not configured",
                status="FAILED",
            )

        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        payload = {
            "to": recipient,
            "text": message,
            "sender": sender_id,
        }

        try:
            response = requests.post(
                self.PINDO_URL,
                json=payload,
                headers=headers,
                timeout=10.0,
            )
            raw_data = response.json() if response.content else {}

            if response.status_code in (200, 201):
                msg_id = str(raw_data.get("id") or raw_data.get("message_id") or "")
                return SMSDeliveryResult(
                    success=True,
                    message_id=msg_id,
                    status="SENT",
                    raw_response=raw_data,
                )
            else:
                error_desc = raw_data.get("message") or raw_data.get("error") or response.text
                logger.warning(
                    "Pindo SMS dispatch rejected | status=%s to=…%s error=%s",
                    response.status_code,
                    recipient[-4:],
                    error_desc,
                )
                return SMSDeliveryResult(
                    success=False,
                    status="FAILED",
                    raw_response=raw_data,
                    error_message=f"HTTP {response.status_code}: {error_desc}",
                )
        except requests.RequestException as exc:
            logger.error("Pindo network exception | to=…%s error=%s", recipient[-4:], exc)
            return SMSDeliveryResult(
                success=False,
                status="FAILED",
                error_message=str(exc),
            )
