import hashlib
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel, UUIDModel


class OTPVerification(UUIDModel, TimeStampedModel):
    """
    Stores phone-based OTP codes for registration and login verification.

    Security:
    - OTP codes are stored hashed (never plaintext).
    - Each code expires after OTP_EXPIRY_MINUTES.
    - Rate-limited at the view level (max 5 requests/hour per phone).
    - Auto-invalidated after successful verification.
    """

    PURPOSES = [
        ("REGISTRATION", "Account Registration"),
        ("LOGIN", "Login Verification"),
        ("PHONE_CHANGE", "Phone Number Change"),
        ("PASSWORD_RESET", "Password Reset"),
        ("IREMBO_BOOKING", "Irembo Booking Confirmation"),
    ]

    phone_number = models.CharField(
        _("Phone Number"),
        max_length=20,
        db_index=True,
    )
    otp_hash = models.CharField(
        _("OTP Hash"),
        max_length=128,
        help_text=_("SHA-256 hash of the OTP code. Never store the raw code."),
    )
    purpose = models.CharField(
        _("Purpose"),
        max_length=30,
        choices=PURPOSES,
        default="REGISTRATION",
    )
    expires_at = models.DateTimeField(_("Expires At"))
    is_used = models.BooleanField(_("Used"), default=False)
    attempt_count = models.PositiveSmallIntegerField(
        _("Attempt Count"),
        default=0,
        help_text=_("Number of failed verification attempts for this code."),
    )

    class Meta:
        app_label = 'accounts'
        verbose_name = _("OTP Verification")
        verbose_name_plural = _("OTP Verifications")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["phone_number", "purpose", "is_used"]),
        ]

    def __str__(self) -> str:
        return f"OTP [{self.purpose}] for {self.phone_number} — expires {self.expires_at}"

    @property
    def is_expired(self) -> bool:
        return timezone.now() > self.expires_at

    @property
    def is_valid(self) -> bool:
        return not self.is_used and not self.is_expired

    def mark_used(self) -> None:
        """Invalidate this OTP after successful verification."""
        self.is_used = True
        self.save(update_fields=["is_used"])

    def increment_attempts(self) -> None:
        """Track failed attempts for rate limiting."""
        self.attempt_count += 1
        self.save(update_fields=["attempt_count"])

    @classmethod
    def hash_otp(cls, raw_otp: str) -> str:
        """Return a SHA-256 hex digest of the raw OTP code."""
        return hashlib.sha256(raw_otp.encode()).hexdigest()
