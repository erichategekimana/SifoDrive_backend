"""
apps/accounts/serializers.py
==============================
DRF serializers for authentication, registration, and profile management.

Consent rules enforced here:
  - Guest registration  → terms_of_service_accepted required (privacy policy skipped)
  - Student registration → both terms_of_service_accepted AND privacy_policy_accepted required
  - Guest → Student upgrade → privacy_policy_accepted required at upgrade time (if not already set)
  - Sensitive fields (national_id, OTP hash) are write-only, never returned in responses.
"""

from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from apps.core.utils import normalize_phone_number
from .constants import AccountStatus, UserRole
from .models import OTPVerification, StudentProfile

User = get_user_model()


# ---------------------------------------------------------------------------
# JWT Customization
# ---------------------------------------------------------------------------

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Extends the default JWT payload with user role, name, status, and consent flags.
    The frontend can use these claims to decide which modals to show (TOS, privacy policy)
    without an extra /me call on every login.
    """

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["role"] = user.role
        token["full_name"] = user.full_name
        token["status"] = user.status
        token["student_id"] = user.student_id
        # Consent state — drives frontend modal flows
        token["terms_accepted"] = user.terms_of_service_accepted
        token["privacy_accepted"] = user.privacy_policy_accepted
        return token


# ---------------------------------------------------------------------------
# Base Registration Mixin
# ---------------------------------------------------------------------------

class BaseRegistrationSerializer(serializers.ModelSerializer):
    """
    Shared validation logic for all registration paths.
    Subclasses control which consent fields are required.
    """

    phone_number = serializers.CharField(
        max_length=20,
        help_text=_("Rwandan phone number (MTN or Airtel). E.g. 0781234567 or +250781234567"),
    )
    password = serializers.CharField(
        write_only=True,
        min_length=8,
        style={"input_type": "password"},
        help_text=_("At least 8 characters."),
    )

    def validate_phone_number(self, value: str) -> str:
        normalized = normalize_phone_number(value)
        if not normalized:
            raise serializers.ValidationError(
                _("Invalid phone number. Please enter a valid Rwandan number.")
            )
        if User.objects.filter(phone_number=normalized).exists():
            raise serializers.ValidationError(
                _("An account with this phone number already exists.")
            )
        return normalized

    def validate_email(self, value: str) -> str:
        if value and User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError(
                _("An account with this email address already exists.")
            )
        return value.lower() if value else value


# ---------------------------------------------------------------------------
# Guest Registration
# ---------------------------------------------------------------------------

class GuestRegistrationSerializer(BaseRegistrationSerializer):
    """
    POST /api/v1/auth/register/guest/

    Minimum required fields for a free guest account:
      - first_name, last_name
      - phone_number (will be OTP-verified)
      - password
      - terms_of_service_accepted → MUST be True

    Privacy policy is NOT required here. It will be prompted lazily
    when the guest attempts an action involving identity data.
    """

    terms_of_service_accepted = serializers.BooleanField(
        help_text=_("You must accept the Terms of Service to create an account."),
    )

    class Meta:
        model = User
        fields = [
            "first_name",
            "last_name",
            "phone_number",
            "password",
            "terms_of_service_accepted",
        ]

    def validate_terms_of_service_accepted(self, value: bool) -> bool:
        if not value:
            raise serializers.ValidationError(
                _("You must accept the Terms of Service to create an account.")
            )
        return value

    def create(self, validated_data: dict) -> User:
        password = validated_data.pop("password")
        user = User(
            role=UserRole.GUEST,
            status=AccountStatus.PENDING_VERIFICATION,
            terms_of_service_accepted=True,
            terms_of_service_accepted_at=timezone.now(),
            **validated_data,
        )
        user.set_password(password)
        user.save()
        return user


# ---------------------------------------------------------------------------
# Student Registration
# ---------------------------------------------------------------------------

class StudentRegistrationSerializer(BaseRegistrationSerializer):
    """
    POST /api/v1/auth/register/student/

    Fields for a formal student enrollment application:
      - first_name, last_name
      - phone_number (will be OTP-verified)
      - email (optional but recommended)
      - password
      - terms_of_service_accepted → MUST be True
      - privacy_policy_accepted   → MUST be True (students submit PII immediately)

    Fields that are completed AFTER successful registration + payment:
      - date_of_birth
      - profile_photo
      - national_id (Indangamuntu)
      - Student ID (auto-generated after tuition payment confirmed)
    """

    email = serializers.EmailField(
        required=False,
        allow_blank=True,
        allow_null=True,
        help_text=_("Optional. Useful for receiving email notifications."),
    )
    terms_of_service_accepted = serializers.BooleanField(
        help_text=_("You must accept the Terms of Service."),
    )
    privacy_policy_accepted = serializers.BooleanField(
        help_text=_(
            "You must accept the Privacy Policy. We will collect and process "
            "your identity data to enroll you (Rwanda Law No 058/2021)."
        ),
    )

    class Meta:
        model = User
        fields = [
            "first_name",
            "last_name",
            "phone_number",
            "email",
            "password",
            "terms_of_service_accepted",
            "privacy_policy_accepted",
        ]

    def validate_terms_of_service_accepted(self, value: bool) -> bool:
        if not value:
            raise serializers.ValidationError(
                _("You must accept the Terms of Service to register.")
            )
        return value

    def validate_privacy_policy_accepted(self, value: bool) -> bool:
        if not value:
            raise serializers.ValidationError(
                _(
                    "Students must accept the Privacy Policy at registration "
                    "since we collect identity data during enrollment."
                )
            )
        return value

    def create(self, validated_data: dict) -> User:
        password = validated_data.pop("password")
        now = timezone.now()
        user = User(
            role=UserRole.STUDENT,
            status=AccountStatus.PENDING_VERIFICATION,
            terms_of_service_accepted=True,
            terms_of_service_accepted_at=now,
            privacy_policy_accepted=True,
            privacy_policy_accepted_at=now,
            **validated_data,
        )
        user.set_password(password)
        user.save()
        return user


# ---------------------------------------------------------------------------
# Guest → Student Upgrade
# ---------------------------------------------------------------------------

class GuestUpgradeSerializer(serializers.Serializer):
    """
    POST /api/v1/auth/upgrade/student/

    Allows an existing GUEST to upgrade their account to STUDENT.
    The guest must accept the privacy policy at this point (if not already done)
    since we will now process their identity data for enrollment.

    Fields already on file (from guest registration) — NOT re-submitted:
      - first_name, last_name, phone_number, password

    Newly required at upgrade:
      - privacy_policy_accepted → MUST be True if not already accepted
    """

    privacy_policy_accepted = serializers.BooleanField(
        help_text=_(
            "You must accept the Privacy Policy before upgrading to a Student account. "
            "We will collect and process your identity data for enrollment."
        ),
    )

    def validate_privacy_policy_accepted(self, value: bool) -> bool:
        if not value:
            raise serializers.ValidationError(
                _("You must accept the Privacy Policy to upgrade to a student account.")
            )
        return value

    def validate(self, attrs: dict) -> dict:
        user = self.context["request"].user
        if user.role != UserRole.GUEST:
            raise serializers.ValidationError(
                _("Only guest accounts can be upgraded to student.")
            )
        return attrs


# ---------------------------------------------------------------------------
# Consent Acceptance Serializers
# ---------------------------------------------------------------------------

class AcceptTermsOfServiceSerializer(serializers.Serializer):
    """
    POST /api/v1/auth/consent/terms/
    Explicit Terms of Service acceptance (used for legacy accounts or re-acceptance flows).
    """

    accepted = serializers.BooleanField(
        help_text=_("Set to true to confirm acceptance of the Terms of Service."),
    )

    def validate_accepted(self, value: bool) -> bool:
        if not value:
            raise serializers.ValidationError(_("You must set accepted to true."))
        return value


class AcceptPrivacyPolicySerializer(serializers.Serializer):
    """
    POST /api/v1/auth/consent/privacy-policy/

    Lazy privacy policy acceptance for guest users.
    This endpoint is called by the frontend when a guest clicks
    'Accept & Continue' on the privacy policy modal before an identity action.
    """

    accepted = serializers.BooleanField(
        help_text=_(
            "Set to true to confirm you have read and accept the Privacy Policy "
            "before submitting your identity data."
        ),
    )

    def validate_accepted(self, value: bool) -> bool:
        if not value:
            raise serializers.ValidationError(
                _("You must accept the Privacy Policy to proceed with this action.")
            )
        return value


# ---------------------------------------------------------------------------
# OTP Serializers
# ---------------------------------------------------------------------------

class OTPRequestSerializer(serializers.Serializer):
    """Request a new OTP code for a given phone number and purpose."""

    phone_number = serializers.CharField(max_length=20)
    purpose = serializers.ChoiceField(choices=OTPVerification.PURPOSES, default="LOGIN")

    def validate_phone_number(self, value: str) -> str:
        normalized = normalize_phone_number(value)
        if not normalized:
            raise serializers.ValidationError(_("Invalid phone number."))
        return normalized


class OTPVerifySerializer(serializers.Serializer):
    """Verify a submitted OTP code. Returns JWT tokens on success."""

    phone_number = serializers.CharField(max_length=20)
    otp_code = serializers.CharField(
        max_length=6,
        min_length=4,
        help_text=_("The 6-digit code sent to your phone."),
    )
    purpose = serializers.ChoiceField(choices=OTPVerification.PURPOSES, default="LOGIN")

    def validate_phone_number(self, value: str) -> str:
        normalized = normalize_phone_number(value)
        if not normalized:
            raise serializers.ValidationError(_("Invalid phone number."))
        return normalized


# ---------------------------------------------------------------------------
# Profile Serializers
# ---------------------------------------------------------------------------

class UserProfileSerializer(serializers.ModelSerializer):
    """
    GET / PATCH /api/v1/auth/me/
    Full profile for the authenticated user. Sensitive fields are excluded.
    """

    full_name = serializers.CharField(read_only=True)
    has_accepted_terms = serializers.BooleanField(read_only=True)
    has_accepted_privacy_policy = serializers.BooleanField(read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "phone_number",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "role",
            "status",
            "student_id",
            "profile_photo",
            "date_of_birth",
            # Consent state (read-only; use /consent/ endpoints to change)
            "has_accepted_terms",
            "has_accepted_privacy_policy",
            "terms_of_service_accepted_at",
            "privacy_policy_accepted_at",
            "created_at",
            "last_login",
        ]
        read_only_fields = [
            "id",
            "phone_number",
            "role",
            "status",
            "student_id",
            "has_accepted_terms",
            "has_accepted_privacy_policy",
            "terms_of_service_accepted_at",
            "privacy_policy_accepted_at",
            "created_at",
            "last_login",
        ]


class StudentProfileSerializer(serializers.ModelSerializer):
    """Student-specific extended profile (language, license category, streak)."""

    class Meta:
        model = StudentProfile
        fields = [
            "preferred_language",
            "license_category",
            "enrollment_date",
            "current_streak_days",
            "longest_streak_days",
            "last_activity_date",
        ]
        read_only_fields = [
            "enrollment_date",
            "current_streak_days",
            "longest_streak_days",
            "last_activity_date",
        ]


class AdminUserListSerializer(serializers.ModelSerializer):
    """Compact user representation for admin list views."""

    class Meta:
        model = User
        fields = [
            "id",
            "phone_number",
            "full_name",
            "email",
            "role",
            "status",
            "student_id",
            "terms_of_service_accepted",
            "privacy_policy_accepted",
            "created_at",
        ]
        read_only_fields = fields
