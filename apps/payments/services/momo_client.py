"""
apps/payments/services/momo_client.py
=====================================
MTN Mobile Money (MoMo) API Client for Collection (Request to Pay).
Supports both MTN Sandbox and Production environments.
"""
import base64
import logging
import time
from typing import Any, Dict, Optional
from decimal import Decimal

import httpx
from django.conf import settings

from apps.core.utils import PhoneNumberUtils

logger = logging.getLogger(__name__)


class MTNMomoException(Exception):
    """Custom exception raised when an MTN MoMo API call fails."""
    def __init__(self, message: str, status_code: Optional[int] = None, details: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details


class MTNMomoClient:
    """
    Client for interacting with MTN MoMo Collection API.
    Handles token authentication, token caching, RequestToPay, and transaction status polling.
    """

    def __init__(self):
        momo_cfg = getattr(settings, "MTN_MOMO", {})
        self.base_url = (momo_cfg.get("BASE_URL") or "https://sandbox.momodeveloper.mtn.com").rstrip("/")
        self.subscription_key = (momo_cfg.get("SUBSCRIPTION_KEY") or "").strip()
        self.api_user = (momo_cfg.get("API_USER") or "").strip()
        self.api_key = (momo_cfg.get("API_KEY") or "").strip()
        self.environment = (momo_cfg.get("ENVIRONMENT") or "sandbox").strip()
        
        # In MTN Sandbox, MTN requires currency 'EUR'. In production, it uses 'RWF'.
        configured_currency = (momo_cfg.get("CURRENCY") or "RWF").strip()
        if self.environment == "sandbox":
            self.currency = "EUR"
        else:
            self.currency = configured_currency

        self._cached_token: Optional[str] = None
        self._token_expires_at: float = 0.0

    def _get_basic_auth_header(self) -> str:
        """Encodes api_user:api_key in Base64 for HTTP Basic Authentication."""
        auth_bytes = f"{self.api_user}:{self.api_key}".encode("utf-8")
        return f"Basic {base64.b64encode(auth_bytes).decode('utf-8')}"

    def get_token(self, force_refresh: bool = False) -> str:
        """
        Obtains or refreshes an OAuth 2.0 Bearer access token from MTN MoMo.
        Tokens are typically valid for 3600 seconds.
        """
        now = time.time()
        if not force_refresh and self._cached_token and now < self._token_expires_at:
            return self._cached_token

        if not self.subscription_key or not self.api_user or not self.api_key:
            raise MTNMomoException("MTN MoMo credentials (Subscription Key, API User, API Key) are not configured.")

        # Note: MTN MoMo Collection token endpoint strictly requires trailing slash
        token_url = f"{self.base_url}/collection/token/"
        headers = {
            "Ocp-Apim-Subscription-Key": self.subscription_key,
            "Authorization": self._get_basic_auth_header(),
        }

        try:
            with httpx.Client(timeout=15.0) as client:
                response = client.post(token_url, headers=headers, content=b"")

            if response.status_code != 200:
                logger.error("Failed to generate MTN MoMo token: HTTP %s - %s", response.status_code, response.text)
                raise MTNMomoException(
                    f"Authentication with MTN MoMo failed (HTTP {response.status_code}).",
                    status_code=response.status_code,
                    details=response.text,
                )

            data = response.json()
            token = data.get("access_token")
            expires_in = int(data.get("expires_in", 3600))

            if not token:
                raise MTNMomoException("No access_token returned by MTN MoMo token endpoint.")

            self._cached_token = token
            # Expire cache 60 seconds before actual expiry to avoid race conditions
            self._token_expires_at = now + max(0, expires_in - 60)
            logger.info("Successfully obtained new MTN MoMo access token (expires in %ds).", expires_in)
            return token

        except httpx.RequestError as exc:
            logger.error("Network error while connecting to MTN MoMo token endpoint: %s", exc)
            raise MTNMomoException(f"Network error connecting to MTN MoMo: {str(exc)}")

    def request_to_pay(
        self,
        reference_id: str,
        amount: Any,
        payer_phone: str,
        external_id: str,
        payer_message: str = "Payment for SifoDrive practice exams",
        payee_note: str = "SifoDrive Exam Credits",
    ) -> Dict[str, Any]:
        """
        Sends RequestToPay to prompt the customer's phone to enter their MoMo PIN.
        
        :param reference_id: UUID string uniquely identifying this transaction
        :param amount: Amount to charge
        :param payer_phone: Phone number to charge (e.g. 0780842458 or +250780842458)
        :param external_id: Reference ID in SifoDrive
        :param payer_message: Message displayed on the payer's phone
        :param payee_note: Note attached to transaction
        :return: Dict containing reference_id and status 'PENDING'
        """
        token = self.get_token()

        # Clean and format phone number to national digits without '+' (e.g. 250780842458)
        normalized = PhoneNumberUtils.normalize(payer_phone) or payer_phone.replace(" ", "").replace("-", "")
        clean_phone = normalized.lstrip("+")

        # Amount as integer or string
        amount_str = str(int(Decimal(str(amount))))

        rtp_url = f"{self.base_url}/collection/v1_0/requesttopay"
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Reference-Id": reference_id,
            "X-Target-Environment": self.environment,
            "Ocp-Apim-Subscription-Key": self.subscription_key,
            "Content-Type": "application/json",
        }

        payload = {
            "amount": amount_str,
            "currency": self.currency,
            "externalId": external_id,
            "payer": {
                "partyIdType": "MSISDN",
                "partyId": clean_phone,
            },
            "payerMessage": payer_message,
            "payeeNote": payee_note,
        }

        logger.info(
            "Sending MTN MoMo RequestToPay: ref=%s, phone=%s, amount=%s %s",
            reference_id, clean_phone, amount_str, self.currency
        )

        try:
            with httpx.Client(timeout=20.0) as client:
                response = client.post(rtp_url, headers=headers, json=payload)

            # 202 Accepted indicates request was received by MTN and queued for push
            if response.status_code not in (200, 202):
                logger.error("MTN MoMo RequestToPay failed: HTTP %s - %s", response.status_code, response.text)
                raise MTNMomoException(
                    f"Payment request rejected by MTN MoMo (HTTP {response.status_code}).",
                    status_code=response.status_code,
                    details=response.text,
                )

            logger.info("MTN MoMo RequestToPay accepted successfully for ref %s.", reference_id)
            return {
                "reference_id": reference_id,
                "status": "PENDING",
                "amount": amount_str,
                "currency": self.currency,
                "payer_phone": clean_phone,
            }

        except httpx.RequestError as exc:
            logger.error("Network error while connecting to MTN MoMo requesttopay: %s", exc)
            raise MTNMomoException(f"Network error connecting to MTN MoMo: {str(exc)}")

    def get_transaction_status(self, reference_id: str) -> Dict[str, Any]:
        """
        Polls the status of a RequestToPay transaction.
        
        Returns:
            Dict containing:
              - status: 'PENDING', 'SUCCESSFUL', or 'FAILED'
              - financialTransactionId: MTN transaction ID (if successful)
              - reason: failure reason (if failed)
        """
        token = self.get_token()
        status_url = f"{self.base_url}/collection/v1_0/requesttopay/{reference_id}"
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Target-Environment": self.environment,
            "Ocp-Apim-Subscription-Key": self.subscription_key,
        }

        try:
            with httpx.Client(timeout=15.0) as client:
                response = client.get(status_url, headers=headers)

            if response.status_code != 200:
                logger.warning(
                    "MTN MoMo status check returned HTTP %s for ref %s: %s",
                    response.status_code, reference_id, response.text
                )
                return {
                    "reference_id": reference_id,
                    "status": "PENDING",
                    "raw_response": response.text,
                }

            data = response.json()
            raw_status = (data.get("status") or "PENDING").upper()

            # MTN statuses: PENDING, SUCCESSFUL, FAILED
            status = raw_status
            if raw_status in ("SUCCESS", "SUCCESSFUL"):
                status = "SUCCESSFUL"
            elif raw_status in ("FAIL", "FAILED", "REJECTED", "TIMEOUT"):
                status = "FAILED"

            return {
                "reference_id": reference_id,
                "status": status,
                "financial_transaction_id": data.get("financialTransactionId"),
                "external_id": data.get("externalId"),
                "amount": data.get("amount"),
                "currency": data.get("currency"),
                "reason": data.get("reason"),
            }

        except httpx.RequestError as exc:
            logger.error("Network error while checking MTN MoMo status for ref %s: %s", reference_id, exc)
            return {
                "reference_id": reference_id,
                "status": "PENDING",
                "error": str(exc),
            }


# Singleton instance for convenience
momo_client = MTNMomoClient()
