"""
apps/notifications/models.py
=============================
Enterprise multi-channel notification models for Sifo Drive.
Supports In-App Notifications, SMS Delivery Logs, Dynamic Templates,
and User Notification Preferences with bilingual (Kinyarwanda & English) support.
"""

from datetime import timedelta
import logging
from typing import Any, Dict, Optional, Tuple

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class NotificationChannel(models.TextChoices):
    SMS = "SMS", _("SMS")
    IN_APP = "IN_APP", _("In-App Notification")
    EMAIL = "EMAIL", _("Email")
    PUSH = "PUSH", _("Push Notification")


class NotificationType(models.TextChoices):
    OTP = "OTP", _("OTP Verification Code")
    WELCOME = "WELCOME", _("Welcome to Sifo Drive")
    GUEST_UPGRADE = "GUEST_UPGRADE", _("Guest Upgraded to Student")
    PAYMENT_SUCCESS = "PAYMENT_SUCCESS", _("Payment Received")
    PAYMENT_FAILED = "PAYMENT_FAILED", _("Payment Failed")
    PAYMENT_REFUNDED = "PAYMENT_REFUNDED", _("Payment Refunded")
    BOOKING_QUEUED = "BOOKING_QUEUED", _("Irembo Slot Queued")
    BOOKING_CONFIRMED = "BOOKING_CONFIRMED", _("Irembo Slot Confirmed")
    BOOKING_SLOTS_EXHAUSTED = "BOOKING_SLOTS_EXHAUSTED", _("Irembo Slots Exhausted")
    BOOKING_REMINDER = "BOOKING_REMINDER", _("Physical Exam Reminder")
    EXAM_RESULT = "EXAM_RESULT", _("Practice Exam Result")
    LIVE_CLASS_SCHEDULED = "LIVE_CLASS_SCHEDULED", _("Live Class Scheduled")
    LIVE_CLASS_REMINDER = "LIVE_CLASS_REMINDER", _("Live Class Starting Soon")
    COURSE_PROGRESS = "COURSE_PROGRESS", _("Course Milestone Reached")
    SECURITY_ALERT = "SECURITY_ALERT", _("Security Alert")
    SYSTEM_ANNOUNCEMENT = "SYSTEM_ANNOUNCEMENT", _("System Announcement")
    GENERAL = "GENERAL", _("General Notification")


class NotificationPriority(models.TextChoices):
    LOW = "LOW", _("Low")
    NORMAL = "NORMAL", _("Normal")
    HIGH = "HIGH", _("High")
    URGENT = "URGENT", _("Urgent")


class NotificationStatus(models.TextChoices):
    PENDING = "PENDING", _("Pending")
    QUEUED = "QUEUED", _("Queued in Worker")
    SENT = "SENT", _("Sent")
    DELIVERED = "DELIVERED", _("Delivered")
    READ = "READ", _("Read")
    FAILED = "FAILED", _("Failed")
    CANCELLED = "CANCELLED", _("Cancelled")


# ---------------------------------------------------------------------------
# QuerySet & Managers
# ---------------------------------------------------------------------------

class NotificationQuerySet(models.QuerySet):
    def unread(self):
        return self.filter(is_read=False)

    def read(self):
        return self.filter(is_read=True)

    def for_user(self, user):
        return self.filter(recipient=user)

    def in_app_feed(self, user):
        """Active in-app notifications for user inbox, ordered newest first."""
        return self.filter(
            recipient=user,
            channel__in=[NotificationChannel.IN_APP, NotificationChannel.SMS],
        ).order_by("-created_at")

    def mark_all_as_read(self, user) -> int:
        now = timezone.now()
        return self.filter(recipient=user, is_read=False).update(
            is_read=True,
            read_at=now,
            status=NotificationStatus.READ,
            updated_at=now,
        )


class NotificationManager(models.Manager.from_queryset(NotificationQuerySet)):
    pass


# ---------------------------------------------------------------------------
# Core In-App & Multi-Channel Notification Model
# ---------------------------------------------------------------------------

class Notification(BaseModel):
    """
    User-facing in-app and unified notification record.
    Acts as the single source of truth for student & tutor inbox feeds.
    """

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notifications",
        verbose_name=_("Recipient"),
        help_text=_("Recipient user. Can be null for guest phone-only OTPs before account creation."),
    )
    recipient_phone = models.CharField(
        _("Recipient Phone"),
        max_length=25,
        blank=True,
        db_index=True,
        help_text=_("E.164 phone number e.g. +250781234567"),
    )
    recipient_email = models.EmailField(
        _("Recipient Email"),
        blank=True,
        default="",
    )
    notification_type = models.CharField(
        _("Type"),
        max_length=40,
        choices=NotificationType.choices,
        default=NotificationType.GENERAL,
        db_index=True,
    )
    channel = models.CharField(
        _("Channel"),
        max_length=20,
        choices=NotificationChannel.choices,
        default=NotificationChannel.IN_APP,
        db_index=True,
    )
    priority = models.CharField(
        _("Priority"),
        max_length=20,
        choices=NotificationPriority.choices,
        default=NotificationPriority.NORMAL,
    )
    title = models.CharField(
        _("Title (EN)"),
        max_length=255,
    )
    title_rw = models.CharField(
        _("Title (RW)"),
        max_length=255,
        blank=True,
        help_text=_("Kinyarwanda title"),
    )
    body = models.TextField(
        _("Body (EN)"),
    )
    body_rw = models.TextField(
        _("Body (RW)"),
        blank=True,
        help_text=_("Kinyarwanda body"),
    )
    action_url = models.CharField(
        _("Action URL"),
        max_length=500,
        blank=True,
        help_text=_("Frontend client route or deep link e.g. /courses/module-1 or /exams/result/123"),
    )
    is_read = models.BooleanField(
        _("Is Read"),
        default=False,
        db_index=True,
    )
    read_at = models.DateTimeField(
        _("Read At"),
        null=True,
        blank=True,
    )
    status = models.CharField(
        _("Status"),
        max_length=20,
        choices=NotificationStatus.choices,
        default=NotificationStatus.PENDING,
        db_index=True,
    )
    metadata = models.JSONField(
        _("Metadata"),
        default=dict,
        blank=True,
        help_text=_("Context data: exam_id, booking_id, amount_rwf, transaction_id, etc."),
    )
    sent_at = models.DateTimeField(
        _("Sent At"),
        null=True,
        blank=True,
    )

    objects = NotificationManager()

    class Meta(BaseModel.Meta):
        verbose_name = _("Notification")
        verbose_name_plural = _("Notifications")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient", "is_read", "-created_at"], name="notif_recipient_read_idx"),
            models.Index(fields=["notification_type", "-created_at"], name="notif_type_created_idx"),
        ]

    def __str__(self):
        user_str = str(self.recipient) if self.recipient else self.recipient_phone
        return f"[{self.channel}] {self.notification_type} → {user_str} ({self.status})"

    def mark_as_read(self) -> None:
        """Mark notification as read with timestamp."""
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.status = NotificationStatus.READ
            self.save(update_fields=["is_read", "read_at", "status", "updated_at"])

    def get_localized_title(self, language: str = "rw") -> str:
        if language == "rw" and self.title_rw:
            return self.title_rw
        return self.title

    def get_localized_body(self, language: str = "rw") -> str:
        if language == "rw" and self.body_rw:
            return self.body_rw
        return self.body


# ---------------------------------------------------------------------------
# SMS Delivery Log Model
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Notification Template Model (Dynamic Admin Templates)
# ---------------------------------------------------------------------------

class NotificationTemplate(BaseModel):
    """
    Dynamic message templates manageable via Django Admin without code redeployment.
    Supports python string interpolation syntax: {student_name}, {otp_code}, etc.
    """

    LANGUAGES = [
        ("rw", _("Kinyarwanda")),
        ("en", _("English")),
        ("fr", _("French")),
    ]

    template_code = models.CharField(
        _("Template Code"),
        max_length=80,
        unique=True,
        db_index=True,
        help_text=_("Unique identifier, e.g. OTP_VERIFICATION, PAYMENT_SUCCESS, IREMBO_CONFIRMED"),
    )
    notification_type = models.CharField(
        _("Notification Type"),
        max_length=40,
        choices=NotificationType.choices,
        db_index=True,
    )
    channel = models.CharField(
        _("Channel"),
        max_length=20,
        choices=NotificationChannel.choices,
        default=NotificationChannel.SMS,
    )
    language = models.CharField(
        _("Language"),
        max_length=10,
        choices=LANGUAGES,
        default="rw",
    )
    title_template = models.CharField(
        _("Title Template"),
        max_length=255,
        blank=True,
        help_text=_("Template for title, e.g. 'Sifo Drive: Kwemeza Konti'"),
    )
    body_template = models.TextField(
        _("Body Template"),
        help_text=_(
            "Template body with variables in {variable_name} format.\n"
            "Example: 'Muraho {name}, kode yawe yo kwiyandikisha muri Sifo Drive ni {otp}. Irangira mu minota {expiry}.'"
        ),
    )
    is_active = models.BooleanField(
        _("Is Active"),
        default=True,
    )
    description = models.CharField(
        _("Description"),
        max_length=255,
        blank=True,
    )

    class Meta(BaseModel.Meta):
        verbose_name = _("Notification Template")
        verbose_name_plural = _("Notification Templates")
        ordering = ["template_code", "language"]

    def __str__(self):
        return f"{self.template_code} [{self.language.upper()}] ({self.channel})"

    def render(self, context: Dict[str, Any]) -> Tuple[str, str]:
        """
        Safely render title and body templates with context dictionary.
        Does not raise KeyError if a variable is missing.
        """
        class SafeDict(dict):
            def __missing__(self, key):
                return f"{{{key}}}"

        safe_ctx = SafeDict(context)
        title = self.title_template.format_map(safe_ctx) if self.title_template else ""
        body = self.body_template.format_map(safe_ctx)
        return title, body


# ---------------------------------------------------------------------------
# Notification Preference Model
# ---------------------------------------------------------------------------

class NotificationPreference(BaseModel):
    """
    Per-user notification delivery settings and language preferences.
    """

    LANGUAGES = [
        ("rw", _("Kinyarwanda")),
        ("en", _("English")),
        ("fr", _("French")),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_preferences",
        verbose_name=_("User"),
    )
    sms_enabled = models.BooleanField(
        _("SMS Notifications Enabled"),
        default=True,
        help_text=_("Receive SMS alerts for important account and exam events."),
    )
    in_app_enabled = models.BooleanField(
        _("In-App Notifications Enabled"),
        default=True,
    )
    email_enabled = models.BooleanField(
        _("Email Notifications Enabled"),
        default=True,
    )
    exam_alerts = models.BooleanField(
        _("Exam Alerts Enabled"),
        default=True,
    )
    booking_alerts = models.BooleanField(
        _("Irembo Booking Alerts Enabled"),
        default=True,
    )
    promo_alerts = models.BooleanField(
        _("Promotional / Marketing Alerts Enabled"),
        default=False,
    )
    preferred_language = models.CharField(
        _("Preferred Language"),
        max_length=10,
        choices=LANGUAGES,
        default="rw",
    )

    class Meta(BaseModel.Meta):
        verbose_name = _("Notification Preference")
        verbose_name_plural = _("Notification Preferences")

    def __str__(self):
        return f"Preferences for {self.user} [{self.preferred_language}]"
