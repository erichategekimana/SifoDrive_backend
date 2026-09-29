from typing import Any, Dict, Tuple
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel
from .choices import NotificationChannel, NotificationType


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
        app_label = "notifications"
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
