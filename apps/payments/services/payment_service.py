"""
apps/payments/services/payment_service.py
=========================================
MTN and Airtel MoMo payment orchestration service.
Handles payment initiation, polling status, and fulfillment.
"""
import logging
import uuid
from typing import Any, Dict, Optional

from apps.payments.services.momo_client import MTNMomoClient, MTNMomoException

logger = logging.getLogger(__name__)


class PaymentService:
    """Orchestrates mobile money transactions across MTN and Airtel."""

    @classmethod
    def initiate_momo_charge(
        cls,
        amount: int,
        payer_phone: str,
        external_id: str,
        payer_message: str = "Payment for exam practice",
        payee_note: str = "SifoDrive Exam Credits",
    ) -> Dict[str, Any]:
        """
        Initiates a MoMo RequestToPay on the customer's phone.
        Returns reference_id and initial status ('PENDING').
        """
        reference_id = str(uuid.uuid4())
        client = MTNMomoClient()

        result = client.request_to_pay(
            reference_id=reference_id,
            amount=amount,
            payer_phone=payer_phone,
            external_id=external_id,
            payer_message=payer_message,
            payee_note=payee_note,
        )

        return result

    @classmethod
    def check_momo_status(cls, reference_id: str) -> Dict[str, Any]:
        """
        Polls the status of an ongoing MoMo transaction from MTN.
        """
        client = MTNMomoClient()
        return client.get_transaction_status(reference_id)

    @classmethod
    def has_active_tuition(cls, user) -> bool:
        """Check if a student has a paid and active tuition subscription."""
        # Future implementation for full school students
        return False
