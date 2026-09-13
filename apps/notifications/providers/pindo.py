"""
apps/notifications/providers/pindo.py
=====================================
Pindo SMS gateway integration for Rwanda (https://api.pindo.io).
Supports standard bearer token authentication, single SMS dispatch to https://api.pindo.io/v1/sms/,
and operational health check diagnostics.
"""

import logging
from typing import Any, Dict, Optional
import requests
from django.conf import settings

from apps.notifications.providers.base import BaseSMSProvider, SMSDeliveryResult

logger = logging.getLogger("apps.notifications.sms.pindo")


class PindoSMSProvider(BaseSMSProvider):
    """
    Client for Pindo SMS API (Rwanda local gateway).
    Base URL: https://api.pindo.io
    Single SMS dispatch endpoint: https://api.pindo.io/v1/sms/
    Doc: https://pindo.io/docs
    """

    DEFAULT_BASE_URL = "https://api.pindo.io"

    def __init__(self, api_token: Optional[str] = None):
        self.api_token = (
            api_token
            or getattr(settings, "PINDO_API_TOKEN", "")
            or getattr(settings, "SMS_API_KEY", "")
        )
        base_url = (getattr(settings, "SMS_GATEWAY_URL", "") or self.DEFAULT_BASE_URL).rstrip("/")
        self.endpoint_url = f"{base_url}/v1/sms/"

    def get_provider_name(self) -> str:
        return "PINDO"

    def send_sms(
        self,
        recipient: str,
        message: str,
        sender_id: Optional[str] = None,
    ) -> SMSDeliveryResult:
        if not self.api_token:
            logger.error("Pindo API token not configured in settings")
            return SMSDeliveryResult(
                success=False,
                error_message="PINDO_API_TOKEN / SMS_API_KEY not configured",
                status="FAILED",
            )

        active_sender = sender_id or getattr(settings, "SMS_SENDER_ID", "PindoTest")

        # Ensure Rwandan international phone format (+250...)
        clean_recipient = recipient.strip()
        if not clean_recipient.startswith("+"):
            if clean_recipient.startswith("250"):
                clean_recipient = f"+{clean_recipient}"
            elif clean_recipient.startswith("0"):
                clean_recipient = f"+250{clean_recipient[1:]}"

        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        payload = {
            "to": clean_recipient,
            "text": message,
            "sender": active_sender,
        }

        try:
            response = requests.post(
                self.endpoint_url,
                json=payload,
                headers=headers,
                timeout=12.0,
            )
            raw_data = response.json() if response.content else {}

            if response.status_code in (200, 201):
                msg_id = str(
                    raw_data.get("sms_id")
                    or raw_data.get("id")
                    or raw_data.get("message_id")
                    or ""
                )
                status_label = str(raw_data.get("status") or "SENT").upper()
                if status_label == "SENT":
                    status_label = "SENT"

                return SMSDeliveryResult(
                    success=True,
                    message_id=msg_id,
                    status=status_label,
                    raw_response=raw_data,
                )
            else:
                error_desc = (
                    raw_data.get("message")
                    or raw_data.get("error")
                    or response.text
                )
                logger.warning(
                    "Pindo SMS dispatch rejected | status=%s to=…%s sender=%s error=%s",
                    response.status_code,
                    clean_recipient[-4:] if len(clean_recipient) >= 4 else clean_recipient,
                    active_sender,
                    error_desc,
                )
                return SMSDeliveryResult(
                    success=False,
                    status="FAILED",
                    raw_response=raw_data,
                    error_message=f"HTTP {response.status_code}: {error_desc}",
                )
        except requests.RequestException as exc:
            logger.error(
                "Pindo network exception | to=…%s error=%s",
                clean_recipient[-4:] if len(clean_recipient) >= 4 else clean_recipient,
                exc,
            )
            return SMSDeliveryResult(
                success=False,
                status="FAILED",
                error_message=str(exc),
            )

    def check_gateway_connectivity(self) -> Dict[str, Any]:
        """
        Operational health check against Pindo API.
        """
        if not self.api_token:
            return {
                "connected": False,
                "provider": "PINDO",
                "endpoint": self.endpoint_url,
                "error": "API token missing",
            }

        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Accept": "application/json",
        }
        try:
            resp = requests.get(self.endpoint_url, headers=headers, timeout=6.0)
            if resp.status_code == 200:
                data = resp.json() if resp.content else {}
                messages_count = len(data.get("sms", []))
                return {
                    "connected": True,
                    "provider": "PINDO",
                    "status_code": resp.status_code,
                    "endpoint": self.endpoint_url,
                    "sender_id": getattr(settings, "SMS_SENDER_ID", "PindoTest"),
                    "recent_outbound_count": messages_count,
                    "message": "Pindo Gateway connected and authenticated.",
                }
            else:
                return {
                    "connected": False,
                    "provider": "PINDO",
                    "status_code": resp.status_code,
                    "endpoint": self.endpoint_url,
                    "error": f"HTTP {resp.status_code}: {resp.text}",
                }
        except Exception as exc:
            return {
                "connected": False,
                "provider": "PINDO",
                "endpoint": self.endpoint_url,
                "error": str(exc),
            }
