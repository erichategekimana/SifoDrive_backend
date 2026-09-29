from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel
from .choices import (
    NotificationChannel,
    NotificationPriority,
    NotificationStatus,
    NotificationType,
)


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
        app_label = "notifications"
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
