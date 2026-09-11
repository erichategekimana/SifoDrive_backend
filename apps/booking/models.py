"""
apps/booking/models.py
======================
Driving Test Booking Concierge (Irembo Registration).
Enables applicants to book an agent to register them for provisional / physical
driving tests on Irembo when slots become available.
"""

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

logger = logging.getLogger("apps.booking.models")


# ---------------------------------------------------------------------------
# Enums & Choices
# ---------------------------------------------------------------------------

class LicenseCategory(models.TextChoices):
    A = "A", _("Category A (Motorcycle / Pikipiki)")
    B = "B", _("Category B (Light Passenger Vehicle / Ikinyabiziga gisanzwe)")
    C = "C", _("Category C (Heavy Goods Vehicle / Truck / Ikamyo)")
    D = "D", _("Category D (Passenger Bus / Bisi)")
    E = "E", _("Category E (Trailer / Remorque)")
    F = "F", _("Category F (Specially Adapted / Special)")


class RwandaDistrict(models.TextChoices):
    # Kigali City
    GASABO = "GASABO", _("Gasabo")
    KICUKIRO = "KICUKIRO", _("Kicukiro")
    NYARUGENGE = "NYARUGENGE", _("Nyarugenge")

    # Northern Province
    BURERA = "BURERA", _("Burera")
    GAKENKE = "GAKENKE", _("Gakenke")
    GICUMBI = "GICUMBI", _("Gicumbi")
    MUSANZE = "MUSANZE", _("Musanze")
    RULINDO = "RULINDO", _("Rulindo")

    # Southern Province
    GISAGARA = "GISAGARA", _("Gisagara")
    HUYE = "HUYE", _("Huye")
    KAMONYI = "KAMONYI", _("Kamonyi")
    MUHANGA = "MUHANGA", _("Muhanga")
    NYAMAGABE = "NYAMAGABE", _("Nyamagabe")
    NYANZA = "NYANZA", _("Nyanza")
    NYARUGURU = "NYARUGURU", _("Nyaruguru")
    RUHANGO = "RUHANGO", _("Ruhango")

    # Eastern Province
    BUGESERA = "BUGESERA", _("Bugesera")
    GATSIBO = "GATSIBO", _("Gatsibo")
    KAYONZA = "KAYONZA", _("Kayonza")
    KIREHE = "KIREHE", _("Kirehe")
    NGOMA = "NGOMA", _("Ngoma")
    NYAGATARE = "NYAGATARE", _("Nyagatare")
    RWAMAGANA = "RWAMAGANA", _("Rwamagana")

    # Western Province
    KARONGI = "KARONGI", _("Karongi")
    NGORORERO = "NGORORERO", _("Ngororero")
    NYABIHU = "NYABIHU", _("Nyabihu")
    NYAMASHEKE = "NYAMASHEKE", _("Nyamasheke")
    RUBAVU = "RUBAVU", _("Rubavu")
    RUSIZI = "RUSIZI", _("Rusizi")
    RUTSIRO = "RUTSIRO", _("Rutsiro")


class KicukiroWorkingSite(models.TextChoices):
    BUSANZA_AUTOMATED = "BUSANZA AUTOMATED CENTER", _("BUSANZA AUTOMATED CENTER")
    BUSANZA_SITE_KIC = "BUSANZA SITE (KIC)", _("BUSANZA SITE (KIC)")


class BookingState(models.TextChoices):
    PENDING = "PENDING", _("Pending — Submitted to System Admin")
    PROCESSING = "PROCESSING", _("Processing — Agent Actively Booking Slot")
    COMPLETED = "COMPLETED", _("Completed — Slot Successfully Booked")
    SLOTS_UNAVAILABLE = "SLOTS_UNAVAILABLE", _("Slots Unavailable — Retained in Queue")
    CANCELLED = "CANCELLED", _("Cancelled")


# ---------------------------------------------------------------------------
# Category Pricing Model
# ---------------------------------------------------------------------------

class CategoryPrice(BaseModel):
    """
    Booking fee pricing per license category.
    Managed exclusively by system administrators.
    """

    category = models.CharField(
        _("License Category"),
        max_length=5,
        choices=LicenseCategory.choices,
        unique=True,
        db_index=True,
    )
    price_rwf = models.PositiveIntegerField(
        _("Price (RWF)"),
        help_text=_("Booking service fee in Rwandan Francs (RWF)"),
    )
    description = models.CharField(
        _("Description"),
        max_length=255,
        blank=True,
    )
    is_active = models.BooleanField(
        _("Is Active"),
        default=True,
    )

    class Meta(BaseModel.Meta):
        verbose_name = _("Category Price")
        verbose_name_plural = _("Category Prices")
        ordering = ["category"]

    def __str__(self):
        return f"Category {self.category}: {self.price_rwf:,} RWF"

    @classmethod
    def get_price_for_category(cls, category: str) -> int:
        """Fetch active price for a category with safe default fallbacks."""
        record = cls.objects.filter(category=category, is_active=True).first()
        if record:
            return record.price_rwf

        # Default standard schedule in RWF if not yet configured by admin
        default_fees = {
            LicenseCategory.A: 5000,
            LicenseCategory.B: 10000,
            LicenseCategory.C: 15000,
            LicenseCategory.D: 15000,
            LicenseCategory.E: 20000,
            LicenseCategory.F: 10000,
        }
        return default_fees.get(category, 10000)


# ---------------------------------------------------------------------------
# Partner Teacher Model
# ---------------------------------------------------------------------------

class PartnerTeacher(BaseModel):
    """
    Private driving instructors partnered with Sifo Drive.
    Managed by administrators; selectable by students during booking.
    """

    first_name = models.CharField(_("First Name"), max_length=100)
    last_name = models.CharField(_("Last Name"), max_length=100)
    phone_number = models.CharField(_("Phone Number"), max_length=25, db_index=True)
    driving_school_affiliation = models.CharField(
        _("Affiliated Driving School"),
        max_length=150,
        blank=True,
        help_text=_("e.g. Inyange Driving School or Independent Instructor"),
    )
    is_active = models.BooleanField(_("Is Active"), default=True)
    notes = models.TextField(_("Internal Notes"), blank=True)

    class Meta(BaseModel.Meta):
        verbose_name = _("Partner Driving Teacher")
        verbose_name_plural = _("Partner Driving Teachers")
        ordering = ["first_name", "last_name"]

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    def __str__(self):
        school = f" - {self.driving_school_affiliation}" if self.driving_school_affiliation else ""
        return f"{self.full_name} ({self.phone_number}){school}"


# ---------------------------------------------------------------------------
# Booking Application Model
# ---------------------------------------------------------------------------

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
