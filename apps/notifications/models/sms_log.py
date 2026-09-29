from typing import Any, Dict, Optional
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel
from .choices import NotificationType
from .notification import Notification


class SMSNotification(BaseModel):
    """
    Audit log of all physical SMS messages dispatched via telecommunication gateways.
    Maintains full backward compatibility with legacy SMSNotification model while
    adding enterprise provider tracking, retry tracking, and status transitions.
    """

    TYPES = NotificationType.choices
    STATUSES = [
        ("PENDING", _("Pending")),
        ("SENT", _("Sent")),
        ("DELIVERED", _("Delivered")),
        ("FAILED", _("Failed")),
    ]

    notification = models.ForeignKey(
        Notification,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sms_logs",
        verbose_name=_("Parent Notification"),
    )
    recipient_phone = models.CharField(
        _("Recipient Phone"),
        max_length=25,
        db_index=True,
    )
    message_type = models.CharField(
        _("Type"),
        max_length=40,
        choices=NotificationType.choices,
        default=NotificationType.OTP,
        db_index=True,
    )
    message_body = models.TextField(
        _("Message Body"),
    )
    sender_id = models.CharField(
        _("Sender ID"),
        max_length=30,
        default="SIFO_DRIVE",
    )
    provider = models.CharField(
        _("SMS Provider"),
        max_length=50,
        default="CONSOLE_MOCK",
        help_text=_("Gateway used: PINDO, AFRICAS_TALKING, HTTP_GATEWAY, CONSOLE_MOCK"),
    )
    provider_message_id = models.CharField(
        _("Provider Message ID"),
        max_length=150,
        blank=True,
        db_index=True,
    )
    status = models.CharField(
        _("Status"),
        max_length=20,
        choices=STATUSES,
        default="PENDING",
        db_index=True,
    )
    retry_count = models.PositiveSmallIntegerField(
        _("Retry Count"),
        default=0,
    )
    error_message = models.TextField(
        _("Error Message"),
        blank=True,
    )
    provider_response = models.JSONField(
        _("Provider Response"),
        null=True,
        blank=True,
    )
    sent_at = models.DateTimeField(
        _("Sent At"),
        null=True,
        blank=True,
    )
    delivered_at = models.DateTimeField(
        _("Delivered At"),
        null=True,
        blank=True,
    )

    class Meta(BaseModel.Meta):
        app_label = "notifications"
        verbose_name = _("SMS Notification Log")
        verbose_name_plural = _("SMS Notification Logs")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient_phone", "-created_at"], name="sms_phone_created_idx"),
            models.Index(fields=["status", "-created_at"], name="sms_status_created_idx"),
        ]

    def __str__(self):
        return f"SMS [{self.message_type}] → {self.recipient_phone} [{self.status}] ({self.provider})"

    def mark_sent(self, message_id: str, raw_response: Dict[str, Any]) -> None:
        self.status = "SENT"
        self.provider_message_id = message_id or ""
        self.provider_response = raw_response
        self.sent_at = timezone.now()
        self.save(update_fields=["status", "provider_message_id", "provider_response", "sent_at", "updated_at"])

    def mark_failed(self, error: str, raw_response: Optional[Dict[str, Any]] = None) -> None:
        self.status = "FAILED"
        self.error_message = error
        if raw_response:
            self.provider_response = raw_response
        self.save(update_fields=["status", "error_message", "provider_response", "updated_at"])

    def mark_delivered(self) -> None:
        self.status = "DELIVERED"
        self.delivered_at = timezone.now()
        self.save(update_fields=["status", "delivered_at", "updated_at"])
