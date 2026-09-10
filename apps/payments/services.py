"""apps/payments/services.py
MTN and Airtel MoMo integration, webhook handling, idempotency."""
import logging
logger = logging.getLogger(__name__)

class PaymentService:
    @classmethod
    def has_active_tuition(cls, user) -> bool:
        """Check if a student has a paid and active tuition subscription."""
        # TODO: implement
        return False
