from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel, UUIDModel
from apps.accounts.constants import (
    AccountStatus,
    UserRole,
)
from apps.accounts.managers import CustomUserManager


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
        app_label = 'accounts'
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
