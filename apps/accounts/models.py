"""
apps/accounts/models.py
========================
Custom User model and OTP verification model for Sifo Drive.

Consent model (two independent flags):
──────────────────────────────────────
  terms_of_service_accepted
      Required for BOTH guests and students at the moment of registration.
      A guest cannot start learning until this is True.

  privacy_policy_accepted
      Required for students at registration (they submit PII immediately).
      For guests it is prompted lazily — only when they attempt an action
      that involves identity data (booking, exam, etc.).
      Use the HasAcceptedPrivacyPolicy permission on those endpoints.

Other design decisions:
- Phone number is the primary login identifier (not username/email).
- Email is optional but unique when provided.
- National ID (Indangamuntu) is stored AES-256 encrypted per Rwanda Law 058/2021.
- Student IDs are generated post-registration after tuition payment is confirmed.
- OTP codes are stored hashed — never in plaintext.
"""

import uuid
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel, UUIDModel
from .constants import (
    AccountStatus,
    CommissionServiceType,
    CommissionStatus,
    LicenseCategory,
    UserRole,
)
from .managers import CustomUserManager


# ---------------------------------------------------------------------------
# User Model
# ---------------------------------------------------------------------------

class User(AbstractBaseUser, PermissionsMixin, UUIDModel, TimeStampedModel):
    """
    Primary user account for all Sifo Drive participants.

    Authentication: Phone number + OTP (primary) or phone + password (admin).
    Identification: Unique phone number in E.164 format (+250XXXXXXXXX).
    """

    # --- Identity ---
    phone_number = models.CharField(
        _("Phone Number"),
        max_length=20,
        unique=True,
        db_index=True,
        help_text=_("Primary identifier. Must be a valid Rwandan phone number in E.164 format."),
    )
    email = models.EmailField(
        _("Email Address"),
        max_length=254,
        unique=True,
        null=True,
        blank=True,
        help_text=_("Optional. Must be unique when provided."),
    )
    first_name = models.CharField(_("First Name"), max_length=100)
    last_name = models.CharField(_("Last Name"), max_length=100)

    # --- Role & Status ---
    role = models.CharField(
        _("Role"),
        max_length=20,
        choices=UserRole.choices,
        default=UserRole.GUEST,
        db_index=True,
    )
    status = models.CharField(
        _("Account Status"),
        max_length=30,
        choices=AccountStatus.choices,
        default=AccountStatus.PENDING_VERIFICATION,
        db_index=True,
    )

    # --- Student-Specific Fields ---
    student_id = models.CharField(
        _("Student ID"),
        max_length=30,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        help_text=_("Auto-generated upon enrollment confirmation. Format: SIFO-STU-YYYY-XXXX"),
    )
    assigned_tutor = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tutoring_students",
        limit_choices_to={"role": UserRole.TUTOR},
        verbose_name=_("Assigned Tutor"),
    )
    created_by_agent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="clients_onboarded",
        limit_choices_to={"role": UserRole.AGENT},
        verbose_name=_("Onboarded by Agent"),
        help_text=_("The Sifo Drive field agent who registered or assisted this client."),
    )

    # --- Enterprise/B2B Fields ---
    school_name = models.CharField(
        _("Driving School Name"),
        max_length=200,
        blank=True,
        default="",
        help_text=_("Only populated for ENTERPRISE_ADMIN accounts."),
    )
    station_quota = models.PositiveSmallIntegerField(
        _("Station Quota"),
        default=1,
        help_text=_("Maximum concurrent exam sessions for this enterprise account."),
    )

    # --- PII: National ID (encrypted at rest) ---
    national_id_encrypted = models.TextField(
        _("National ID (Encrypted)"),
        blank=True,
        default="",
        help_text=_(
            "AES-256 encrypted 16-digit National Identification Number (Indangamuntu). "
            "Never stored in plaintext per Rwanda Law No 058/2021."
        ),
    )

    # --- Profile ---
    profile_photo = models.ImageField(
        _("Profile Photo"),
        upload_to="profiles/photos/%Y/%m/",
        null=True,
        blank=True,
    )
    date_of_birth = models.DateField(
        _("Date of Birth"),
        null=True,
        blank=True,
    )

    # --- Consent (NCSA Compliance) ---
    #
    # Terms of Service — required for everyone at registration.
    terms_of_service_accepted = models.BooleanField(
        _("Terms of Service Accepted"),
        default=False,
        help_text=_(
            "Must be True before a user can access any platform feature. "
            "Required at the point of registration for both guests and students."
        ),
    )
    terms_of_service_accepted_at = models.DateTimeField(
        _("Terms of Service Accepted At"),
        null=True,
        blank=True,
    )
    #
    # Privacy Policy — required at registration for students.
    # For guests, prompted lazily before any identity-collecting action.
    privacy_policy_accepted = models.BooleanField(
        _("Privacy Policy Accepted"),
        default=False,
        help_text=_(
            "Required before collecting any PII or biometrics (Art. 6 & 17). "
            "Students accept at registration; guests are prompted when needed."
        ),
    )
    privacy_policy_accepted_at = models.DateTimeField(
        _("Privacy Policy Accepted At"),
        null=True,
        blank=True,
    )

    # --- Django Auth Fields ---
    is_staff = models.BooleanField(
        _("Staff Status"),
        default=False,
        help_text=_("Designates whether the user can log into the Django admin site."),
    )
    is_active = models.BooleanField(
        _("Active"),
        default=True,
    )
    last_login_ip = models.GenericIPAddressField(
        _("Last Login IP"),
        null=True,
        blank=True,
    )

    # Manager
    objects = CustomUserManager()

    # Auth configuration
    USERNAME_FIELD = "phone_number"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    class Meta:
        verbose_name = _("User")
        verbose_name_plural = _("Users")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["role", "status"]),
            models.Index(fields=["student_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.get_full_name()} ({self.phone_number}) [{self.role}]"

    # --- Properties ---

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    def get_full_name(self) -> str:
        return self.full_name

    def get_short_name(self) -> str:
        return self.first_name

    @property
    def is_student(self) -> bool:
        return self.role == UserRole.STUDENT

    @property
    def is_guest(self) -> bool:
        return self.role == UserRole.GUEST

    @property
    def is_tutor(self) -> bool:
        return self.role == UserRole.TUTOR

    @property
    def is_enterprise_admin(self) -> bool:
        return self.role == UserRole.ENTERPRISE_ADMIN

    @property
    def is_board_reviewer(self) -> bool:
        return self.role == UserRole.BOARD_REVIEWER

    @property
    def is_system_admin(self) -> bool:
        return self.role == UserRole.SYSTEM_ADMIN

    @property
    def is_verified(self) -> bool:
        return self.status == AccountStatus.ACTIVE

    @property
    def is_suspended(self) -> bool:
        return self.status == AccountStatus.SUSPENDED

    @property
    def is_deactivated(self) -> bool:
        return self.status == AccountStatus.DEACTIVATED

    @property
    def is_blacklisted(self) -> bool:
        return self.status == AccountStatus.BLACKLISTED

    # --- PII Encryption Helpers ---

    def set_national_id(self, plaintext_id: str) -> None:
        """Encrypt and store a National ID number. Never store the raw value."""
        from apps.core.utils import get_pii_encryptor
        self.national_id_encrypted = get_pii_encryptor().encrypt(plaintext_id)

    def get_national_id(self) -> str | None:
        """Decrypt and return the National ID. Returns None if not set."""
        if not self.national_id_encrypted:
            return None
        from apps.core.utils import get_pii_encryptor
        return get_pii_encryptor().decrypt(self.national_id_encrypted)

    # --- Consent ---

    @property
    def has_accepted_terms(self) -> bool:
        return self.terms_of_service_accepted

    @property
    def has_accepted_privacy_policy(self) -> bool:
        return self.privacy_policy_accepted

    def accept_terms_of_service(self) -> None:
        """
        Record user's acceptance of the Terms of Service.
        Required for all users before platform access is granted.
        """
        if self.terms_of_service_accepted:
            return  # Idempotent — already accepted
        self.terms_of_service_accepted = True
        self.terms_of_service_accepted_at = timezone.now()
        self.save(update_fields=["terms_of_service_accepted", "terms_of_service_accepted_at"])

    def accept_privacy_policy(self) -> None:
        """
        Record user's affirmative consent to the Privacy Policy.
        Must be called before collecting any PII or biometrics
        (Rwanda Law No 058/2021, Articles 6 & 17).
        """
        if self.privacy_policy_accepted:
            return  # Idempotent — already accepted
        self.privacy_policy_accepted = True
        self.privacy_policy_accepted_at = timezone.now()
        self.save(update_fields=["privacy_policy_accepted", "privacy_policy_accepted_at"])

    # --- Account Lifecycle ---

    def activate(self) -> None:
        """Activate account."""
        self.status = AccountStatus.ACTIVE
        self.is_active = True
        self.save(update_fields=["status", "is_active"])

    def deactivate(self) -> None:
        """Deactivate account."""
        self.status = AccountStatus.DEACTIVATED
        self.is_active = False
        self.save(update_fields=["status", "is_active"])

    def suspend(self) -> None:
        """Suspend account for policy violations."""
        self.status = AccountStatus.SUSPENDED
        self.is_active = False
        self.save(update_fields=["status", "is_active"])

    def blacklist(self) -> None:
        """Blacklist account permanently."""
        self.status = AccountStatus.BLACKLISTED
        self.is_active = False
        self.save(update_fields=["status", "is_active"])


# ---------------------------------------------------------------------------
# OTP Verification Model
# ---------------------------------------------------------------------------

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
        import hashlib
        return hashlib.sha256(raw_otp.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Student Enrollment Profile (extended data for STUDENT role)
# ---------------------------------------------------------------------------

class StudentProfile(UUIDModel, TimeStampedModel):
    """
    Extended profile data for enrolled students.
    Separate from User to keep the core User model lean.
    """

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="student_profile",
        limit_choices_to={"role": UserRole.STUDENT},
    )
    preferred_language = models.CharField(
        _("Preferred Language"),
        max_length=10,
        choices=[("en", "English"), ("rw", "Kinyarwanda")],
        default="en",
    )
    license_category = models.CharField(
        _("License Category"),
        max_length=5,
        choices=LicenseCategory.choices,
        default=LicenseCategory.B,
    )
    enrollment_date = models.DateField(
        _("Enrollment Date"),
        null=True,
        blank=True,
    )

    # --- Gamification ---
    current_streak_days = models.PositiveIntegerField(
        _("Current Streak (Days)"),
        default=0,
    )
    longest_streak_days = models.PositiveIntegerField(
        _("Longest Streak (Days)"),
        default=0,
    )
    last_activity_date = models.DateField(
        _("Last Activity Date"),
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = _("Student Profile")
        verbose_name_plural = _("Student Profiles")

    def __str__(self) -> str:
        return f"Profile — {self.user.student_id or self.user.phone_number}"


# ---------------------------------------------------------------------------
# Agent Profile (extended data for AGENT role)
# ---------------------------------------------------------------------------

class AgentProfile(UUIDModel, TimeStampedModel):
    """
    Profile data for Sifo Drive field/kiosk agents.
    Tracks agent identification, commission accumulation, and 30-day payout cycles.
    """

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="agent_profile",
        limit_choices_to={"role": UserRole.AGENT},
    )
    agent_code = models.CharField(
        _("Agent Code"),
        max_length=30,
        unique=True,
        db_index=True,
        help_text=_("Unique identifier (e.g. SIFO-AGT-001)."),
    )
    business_name = models.CharField(
        _("Kiosk / Agency Business Name"),
        max_length=150,
        blank=True,
        default="",
        help_text=_("Name of the agent's kiosk, cyber café, or agency location."),
    )
    national_id_number = models.CharField(
        _("National ID Number"),
        max_length=30,
        blank=True,
        default="",
    )
    district = models.CharField(_("District"), max_length=50, blank=True, default="")
    sector = models.CharField(_("Sector"), max_length=50, blank=True, default="")
    total_accrued_rwf = models.PositiveIntegerField(
        _("Total Accrued Commissions (RWF)"),
        default=0,
        help_text=_("All-time commission calculated from client services."),
    )
    total_paid_out_rwf = models.PositiveIntegerField(
        _("Total Paid Out (RWF)"),
        default=0,
        help_text=_("All-time commission settled and paid to agent by admin."),
    )
    last_payout_date = models.DateField(
        _("Last Payout Date"),
        null=True,
        blank=True,
        help_text=_("Date of the most recent monthly settlement."),
    )
    is_approved = models.BooleanField(_("Is Approved"), default=True)

    class Meta:
        verbose_name = _("Agent Profile")
        verbose_name_plural = _("Agent Profiles")
        ordering = ["agent_code"]

    def __str__(self) -> str:
        return f"Agent {self.agent_code} — {self.user.full_name or self.user.phone_number}"

    @property
    def pending_balance_rwf(self) -> int:
        """Calculated commission balance awaiting monthly payout."""
        return max(0, self.total_accrued_rwf - self.total_paid_out_rwf)


# ---------------------------------------------------------------------------
# Per-Service Configurable Commission Engine
# ---------------------------------------------------------------------------

class ServiceCommissionConfig(UUIDModel, TimeStampedModel):
    """
    Configurable commission fees per service type.
    System admin can update the commission fee in RWF for any service at any time.
    """

    service_type = models.CharField(
        _("Service Type"),
        max_length=30,
        choices=CommissionServiceType.choices,
        unique=True,
        db_index=True,
    )
    service_name = models.CharField(_("Service Display Name"), max_length=120)
    default_client_price_rwf = models.PositiveIntegerField(
        _("Default Client Price (RWF)"),
        default=2500,
        help_text=_("Standard price charged to clients for this service."),
    )
    commission_fee_rwf = models.PositiveIntegerField(
        _("Agent Commission Fee (RWF)"),
        default=500,
        help_text=_("Flat commission earned by agent per completed service."),
    )
    is_active = models.BooleanField(_("Is Active"), default=True)
    notes = models.TextField(_("Internal Notes"), blank=True, default="")

    class Meta:
        verbose_name = _("Service Commission Config")
        verbose_name_plural = _("Service Commission Configs")
        ordering = ["service_name"]

    def __str__(self) -> str:
        return f"{self.service_name}: {self.commission_fee_rwf} RWF commission"


# ---------------------------------------------------------------------------
# Agent Commission Record (Calculated Ledger)
# ---------------------------------------------------------------------------

class AgentCommission(UUIDModel, TimeStampedModel):
    """
    Commission ledger entry recorded whenever an agent facilitates a client service.
    Money does not go directly to agent immediately; it accumulates as calculated
    earnings settled monthly (every 30 days) by system administrator.
    """

    agent = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="commissions_earned",
        limit_choices_to={"role": UserRole.AGENT},
        verbose_name=_("Agent"),
    )
    client = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="agent_facilitated_services",
        verbose_name=_("Client"),
    )
    service_type = models.CharField(
        _("Service Type"),
        max_length=30,
        choices=CommissionServiceType.choices,
        default=CommissionServiceType.BOOKING,
        db_index=True,
    )
    service_reference = models.CharField(
        _("Service Reference"),
        max_length=100,
        blank=True,
        default="",
        help_text=_("Booking ticket number, payment transaction UUID, or subscription reference."),
    )
    amount_paid_by_client_rwf = models.PositiveIntegerField(
        _("Amount Paid by Client (RWF)"),
        default=2500,
    )
    commission_amount_rwf = models.PositiveIntegerField(
        _("Commission Fee Earned (RWF)"),
        default=500,
    )
    status = models.CharField(
        _("Commission Status"),
        max_length=20,
        choices=CommissionStatus.choices,
        default=CommissionStatus.ACCRUED,
        db_index=True,
    )
    paid_out_at = models.DateTimeField(_("Paid Out At"), null=True, blank=True)
    paid_out_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payouts_administered",
        verbose_name=_("Settled By Admin"),
    )
    payout_batch_id = models.CharField(_("Payout Batch ID"), max_length=50, blank=True, default="")
    notes = models.TextField(_("Internal Remarks"), blank=True, default="")

    class Meta:
        verbose_name = _("Agent Commission Record")
        verbose_name_plural = _("Agent Commission Records")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"[{self.status}] {self.agent.phone_number} — {self.service_type}: {self.commission_amount_rwf} RWF"

