"""
apps/notifications/providers/base.py
====================================
Abstract Base Class for SMS Gateway Providers and common delivery data structures.
Follows the Strategy / Provider pattern to enable pluggable gateways (Pindo,
Africa's Talking, HTTP Gateway, Console Mock).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class SMSDeliveryResult:
    """Standardized result returned by any SMS provider."""
    success: bool
    message_id: Optional[str] = None
    status: str = "PENDING"          # "SENT", "DELIVERED", "FAILED"
    raw_response: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None

    def __post_init__(self):
        if self.success and not self.status:
            self.status = "SENT"
        elif not self.success and not self.status:
            self.status = "FAILED"


class BaseSMSProvider(ABC):
    """
    Abstract interface that all SMS gateway integrations must implement.
    Ensures testability, loose coupling, and seamless provider switching.
    """

    @abstractmethod
    def send_sms(
        self,
        recipient: str,
        message: str,
        sender_id: str = "SIFO_DRIVE",
    ) -> SMSDeliveryResult:
        """
        Send a single SMS message.

        Args:
            recipient: E.164 formatted phone number (e.g. "+250781234567")
            message: Plain text body of the SMS
            sender_id: Alphanumeric sender ID registered with the regulator

        Returns:
            SMSDeliveryResult with status, provider message ID, and raw payload
        """
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """Return the unique provider identifier string."""
        pass
