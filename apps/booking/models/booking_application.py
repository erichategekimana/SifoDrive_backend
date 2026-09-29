from datetime import date
import hashlib
import hmac
import logging
import uuid
from typing import Optional

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel
from apps.core.utils import get_pii_encryptor
from .choices import BookingState, KicukiroWorkingSite, LicenseCategory, RwandaDistrict
from .category_price import CategoryPrice
from .partner_teacher import PartnerTeacher

logger = logging.getLogger("apps.booking.models.booking_application")


class BookingApplication(BaseModel):
    """
    Driving test booking application.
    Submitted by user, processed by system admin / agent, and updated with Irembo billing number.
    """

    STATES = BookingState.choices  # Backward compatibility

    ticket_number = models.CharField(
        _("Ticket Number"),
        max_length=30,
        unique=True,
        db_index=True,
        editable=False,
    )
    applicant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="booking_applications",
        verbose_name=_("Applicant User"),
    )

    # Required Applicant Information
    first_name = models.CharField(_("First Name"), max_length=100)
    last_name = models.CharField(_("Last Name"), max_length=100)
    phone_number = models.CharField(_("Phone Number"), max_length=25, db_index=True)
    national_id_encrypted = models.TextField(
        _("National ID (Encrypted)"),
        help_text=_("AES-256 encrypted 16-digit Rwandan National ID"),
    )
    national_id_hash = models.CharField(
        _("National ID Blind Index"),
        max_length=64,
        db_index=True,
        blank=True,
        help_text=_("HMAC-SHA256 hash for deduplication/lookup without decrypting"),
    )
    date_of_birth = models.DateField(_("Date of Birth"))
    license_category = models.CharField(
        _("License Category"),
        max_length=5,
        choices=LicenseCategory.choices,
        db_index=True,
    )
    preferred_district = models.CharField(
        _("Preferred District"),
        max_length=50,
        choices=RwandaDistrict.choices,
        db_index=True,
    )
    working_site = models.CharField(
        _("Working Site"),
        max_length=50,
        choices=KicukiroWorkingSite.choices,
        null=True,
        blank=True,
        help_text=_("MANDATORY if preferred district is Kicukiro ('BUSANZA AUTOMATED CENTER' or 'BUSANZA SITE (KIC)')"),
    )

    # Optional Partner Teacher
    partner_teacher = models.ForeignKey(
        PartnerTeacher,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="student_bookings",
        verbose_name=_("Partner Driving Teacher"),
        help_text=_("Private instructor who taught the student (optional)"),
    )

    # Financial / Tier Snapshot
    price_rwf = models.PositiveIntegerField(
        _("Price (RWF)"),
        help_text=_("Service price recorded at the time of booking"),
    )

    # Workflow & State
    state = models.CharField(
        _("State"),
        max_length=30,
        choices=BookingState.choices,
        default=BookingState.PENDING,
        db_index=True,
    )

    # Agent & Irembo Completion Details
    assigned_agent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_bookings",
        verbose_name=_("Assigned Admin/Agent"),
    )
    irembo_billing_number = models.CharField(
        _("Irembo Billing Number"),
        max_length=100,
        blank=True,
        db_index=True,
        help_text=_("Attached by admin upon successfully booking the slot on Irembo"),
    )
    irembo_application_number = models.CharField(
        _("Irembo Application Number"),
        max_length=100,
        blank=True,
    )
    confirmed_test_date = models.DateField(
        _("Confirmed Test Date"),
        null=True,
        blank=True,
    )
    confirmed_test_time = models.TimeField(
        _("Confirmed Test Time"),
        null=True,
        blank=True,
    )
    confirmed_venue = models.CharField(
        _("Confirmed Venue"),
        max_length=255,
        blank=True,
    )
    confirmation_pdf = models.FileField(
        _("Confirmation PDF"),
        upload_to="bookings/confirmations/%Y/%m/",
        null=True,
        blank=True,
    )
    agent_notes = models.TextField(
        _("Agent / Admin Notes"),
        blank=True,
    )
    submitted_at = models.DateTimeField(
        _("Submitted At"),
        default=timezone.now,
    )
    completed_at = models.DateTimeField(
        _("Completed At"),
        null=True,
        blank=True,
    )

    class Meta(BaseModel.Meta):
        app_label = "booking"
        verbose_name = _("Booking Application")
        verbose_name_plural = _("Booking Applications")
        ordering = ["-submitted_at"]
        indexes = [
            models.Index(fields=["applicant", "state", "-submitted_at"], name="bk_app_state_idx"),
            models.Index(fields=["license_category", "state"], name="bk_cat_state_idx"),
            models.Index(fields=["preferred_district", "state"], name="bk_dist_state_idx"),
        ]

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    def __str__(self):
        return f"Booking {self.ticket_number} — {self.full_name} [{self.state}]"

    def clean(self):
        super().clean()
        # 1. Validate Kicukiro working site requirement
        if self.preferred_district == RwandaDistrict.KICUKIRO:
            if not self.working_site:
                raise ValidationError({
                    "working_site": _(
                        "For Kicukiro district, selecting a working site is required. "
                        "Options: 'BUSANZA AUTOMATED CENTER' or 'BUSANZA SITE (KIC)'."
                    )
                })
            if self.working_site not in KicukiroWorkingSite.values:
                raise ValidationError({
                    "working_site": _(
                        f"Invalid site for Kicukiro. Must be one of: {list(KicukiroWorkingSite.values)}"
                    )
                })
        else:
            # If district is not Kicukiro, working_site should be null/empty
            if self.working_site:
                self.working_site = None

        # 2. Minimum age validation (18 years for driving test in Rwanda)
        if self.date_of_birth:
            today = date.today()
            age = today.year - self.date_of_birth.year - (
                (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
            )
            if age < 18:
                raise ValidationError({
                    "date_of_birth": _("Applicant must be at least 18 years old to apply for a driving test.")
                })

    def save(self, *args, **kwargs):
        # Generate ticket number if not set
        if not self.ticket_number:
            prefix = "BK"
            year = timezone.now().strftime("%Y%m")
            short_id = uuid.uuid4().hex[:6].upper()
            self.ticket_number = f"{prefix}-{year}-{short_id}"

        # Assign price snapshot from CategoryPrice if not set
        if not self.price_rwf:
            self.price_rwf = CategoryPrice.get_price_for_category(self.license_category)

        self.full_clean()
        super().save(*args, **kwargs)

    @classmethod
    def compute_nid_hash(cls, nid: str) -> str:
        """Compute blind HMAC-SHA256 for National ID matching without decryption."""
        secret = getattr(settings, "PII_ENCRYPTION_KEY", "sifo-default-secret").encode()
        return hmac.new(secret, nid.strip().encode(), hashlib.sha256).hexdigest()

    def set_national_id(self, nid: str) -> None:
        """Encrypt and set National ID along with blind index."""
        cleaned = nid.strip()
        encryptor = get_pii_encryptor()
        self.national_id_encrypted = encryptor.encrypt(cleaned)
        self.national_id_hash = self.compute_nid_hash(cleaned)

    def get_decrypted_national_id(self) -> Optional[str]:
        """Decrypt National ID using AES-256 Fernet."""
        if not self.national_id_encrypted:
            return None
        encryptor = get_pii_encryptor()
        return encryptor.decrypt(self.national_id_encrypted)


# Alias for backward compatibility
BookingOrder = BookingApplication
