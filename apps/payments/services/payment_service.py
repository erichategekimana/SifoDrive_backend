"""
apps/payments/services/payment_service.py
=========================================
MTN and Airtel MoMo payment orchestration service.
Handles payment initiation, polling status, PostgreSQL transaction logging,
and asynchronous webhook fulfillment.
"""
import logging
import uuid
from typing import Any, Dict, Optional

from django.utils import timezone

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
        reference_id: Optional[str] = None,
        recipient_phone: Optional[str] = None,
        package_key: str = "",
        credits_added: int = 0,
        user: Optional[Any] = None,
        fee_type: str = "PRACTICE_EXAM_CREDITS",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Initiates a MoMo RequestToPay on the customer's phone and logs the
        initial transaction to PostgreSQL.
        """
        ref_id = reference_id or str(uuid.uuid4())
        client = MTNMomoClient()

        # Send RequestToPay to MTN MoMo
        result = client.request_to_pay(
            reference_id=ref_id,
            amount=amount,
            payer_phone=payer_phone,
            external_id=external_id,
            payer_message=payer_message,
            payee_note=payee_note,
        )

        # Record to PostgreSQL Transaction model
        cls.record_pending_transaction(
            reference_id=ref_id,
            amount=amount,
            payer_phone=payer_phone,
            recipient_phone=recipient_phone or payer_phone,
            external_id=external_id,
            fee_type=fee_type,
            package_key=package_key,
            credits_added=credits_added,
            user=user,
            metadata=metadata,
        )

        return result

    @classmethod
    def record_pending_transaction(
        cls,
        reference_id: str,
        amount: int,
        payer_phone: str,
        recipient_phone: str,
        external_id: str,
        fee_type: str = "PRACTICE_EXAM_CREDITS",
        package_key: str = "",
        credits_added: int = 0,
        user: Optional[Any] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Attempts to log the initiated transaction into PostgreSQL Transaction table."""
        try:
            from apps.payments.models import Transaction
            from apps.core.utils import PhoneNumberUtils

            payer_user = user if (user and getattr(user, 'is_authenticated', False)) else None
            clean_payer = PhoneNumberUtils.normalize(payer_phone) or payer_phone
            clean_recipient = PhoneNumberUtils.normalize(recipient_phone) or recipient_phone

            meta = metadata or {}
            meta["external_id"] = external_id

            ref_uuid = uuid.UUID(reference_id) if isinstance(reference_id, str) else reference_id

            Transaction.objects.create(
                payer=payer_user,
                phone_number=clean_payer,
                recipient_phone=clean_recipient,
                provider="MTN",
                fee_type=fee_type,
                amount=amount,
                currency="RWF",
                status="PENDING",
                idempotency_key=ref_uuid,
                package_key=package_key,
                credits_added=credits_added,
                metadata=meta,
            )
            logger.info("Recorded Transaction in PostgreSQL [PENDING]: ref=%s, phone=%s, amount=%s", reference_id, clean_payer, amount)
        except Exception as exc:
            logger.warning("Could not persist Transaction in PostgreSQL (fallback to JSON ledger active): %s", exc)

    @classmethod
    def record_successful_transaction(
        cls,
        reference_id: str,
        financial_transaction_id: Optional[str] = None,
        webhook_payload: Optional[Dict[str, Any]] = None,
    ):
        """Updates PostgreSQL Transaction record to SUCCESSFUL with provider transaction ID."""
        try:
            from apps.payments.models import Transaction
            ref_uuid = uuid.UUID(reference_id) if isinstance(reference_id, str) else reference_id
            tx = Transaction.objects.filter(idempotency_key=ref_uuid).first()
            if tx:
                tx.status = "SUCCESSFUL"
                if financial_transaction_id:
                    tx.provider_transaction_id = str(financial_transaction_id)
                tx.completed_at = timezone.now()
                if webhook_payload:
                    tx.webhook_payload = webhook_payload
                tx.save(update_fields=["status", "provider_transaction_id", "completed_at", "webhook_payload", "updated_at"])
                logger.info("Updated Transaction in PostgreSQL [SUCCESSFUL]: ref=%s, tx_id=%s", reference_id, financial_transaction_id)
        except Exception as exc:
            logger.warning("Could not update Transaction in PostgreSQL: %s", exc)

    @classmethod
    def record_failed_transaction(
        cls,
        reference_id: str,
        reason: Optional[str] = None,
        webhook_payload: Optional[Dict[str, Any]] = None,
    ):
        """Updates PostgreSQL Transaction record to FAILED."""
        try:
            from apps.payments.models import Transaction
            ref_uuid = uuid.UUID(reference_id) if isinstance(reference_id, str) else reference_id
            tx = Transaction.objects.filter(idempotency_key=ref_uuid).first()
            if tx:
                tx.status = "FAILED"
                tx.failed_reason = reason or "Payment failed or rejected"
                if webhook_payload:
                    tx.webhook_payload = webhook_payload
                tx.save(update_fields=["status", "failed_reason", "webhook_payload", "updated_at"])
                logger.info("Updated Transaction in PostgreSQL [FAILED]: ref=%s, reason=%s", reference_id, reason)
        except Exception as exc:
            logger.warning("Could not update Transaction to FAILED in PostgreSQL: %s", exc)

    @classmethod
    def check_momo_status(cls, reference_id: str) -> Dict[str, Any]:
        """Polls the status of an ongoing MoMo transaction from MTN."""
        client = MTNMomoClient()
        return client.get_transaction_status(reference_id)

    @classmethod
    def handle_momo_webhook(
        cls,
        payload: Dict[str, Any],
        headers: Dict[str, Any],
        query_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Processes incoming webhook callbacks from MTN MoMo.
        Extracts reference ID and status, fulfills exam credits, and updates PostgreSQL.
        """
        from apps.examinations.services.credit_service import ExamCreditService

        # Extract transaction reference from headers, query params, or body
        ref_id = (
            headers.get("X-Reference-Id")
            or headers.get("x-reference-id")
            or query_params.get("ref")
            or query_params.get("reference_id")
            or payload.get("referenceId")
            or payload.get("reference_id")
        )

        financial_tx_id = payload.get("financialTransactionId") or payload.get("financial_transaction_id")
        raw_status = (payload.get("status") or "").upper()

        # If reference ID is missing in header/body, attempt to match externalId
        if not ref_id and payload.get("externalId"):
            ext_id = str(payload.get("externalId"))
            pending = ExamCreditService._load_pending_payments()
            for k, item in pending.items():
                if item.get("external_id") == ext_id:
                    ref_id = k
                    break

        if not ref_id:
            logger.error("MoMo webhook received without reference ID: %s", payload)
            return {
                "success": False,
                "message": "Missing transaction reference ID in webhook callback.",
            }

        ref_str = str(ref_id)
        logger.info("Processing MoMo webhook for ref=%s, status=%s, tx_id=%s", ref_str, raw_status, financial_tx_id)

        if raw_status in ("SUCCESS", "SUCCESSFUL"):
            fulfillment = ExamCreditService.fulfill_successful_momo_payment(
                reference_id=ref_str,
                financial_transaction_id=financial_tx_id,
                webhook_payload=payload,
            )
            cls.record_successful_transaction(
                reference_id=ref_str,
                financial_transaction_id=financial_tx_id,
                webhook_payload=payload,
            )
            return {
                "success": True,
                "reference_id": ref_str,
                "payment_status": "SUCCESSFUL",
                "message": fulfillment.get("message", "Payment fulfilled successfully."),
            }

        elif raw_status in ("FAIL", "FAILED", "REJECTED", "TIMEOUT"):
            reason = payload.get("reason") or "Payment was rejected or cancelled on customer device."
            ExamCreditService.mark_payment_failed(
                reference_id=ref_str,
                reason=reason,
                webhook_payload=payload,
            )
            cls.record_failed_transaction(
                reference_id=ref_str,
                reason=reason,
                webhook_payload=payload,
            )
            return {
                "success": True,
                "reference_id": ref_str,
                "payment_status": "FAILED",
                "message": reason,
            }

        return {
            "success": True,
            "reference_id": ref_str,
            "payment_status": raw_status or "PENDING",
            "message": "Callback received for pending transaction.",
        }

    @classmethod
    def has_active_tuition(cls, user) -> bool:
        """Check if a student has a paid and active tuition subscription."""
        return False
