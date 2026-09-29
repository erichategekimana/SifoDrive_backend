from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


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
        app_label = "notifications"
        verbose_name = _("Notification Preference")
        verbose_name_plural = _("Notification Preferences")

    def __str__(self):
        return f"Preferences for {self.user} [{self.preferred_language}]"
