"""
apps/accounts/managers.py
==========================
Custom manager and queryset for the User model.
Provides role-specific querysets and safe user creation helpers.
"""

from django.contrib.auth.models import BaseUserManager
from django.utils.translation import gettext_lazy as _

from .constants import AccountStatus, UserRole


class UserQuerySet:
    """Mixin providing role-filter shortcuts on any User queryset."""

    def students(self):
        return self.filter(role=UserRole.STUDENT)

    def guests(self):
        return self.filter(role=UserRole.GUEST)

    def tutors(self):
        return self.filter(role=UserRole.TUTOR)

    def enterprise_admins(self):
        return self.filter(role=UserRole.ENTERPRISE_ADMIN)

    def board_reviewers(self):
        return self.filter(role=UserRole.BOARD_REVIEWER)

    def system_admins(self):
        return self.filter(role=UserRole.SYSTEM_ADMIN)

    def active(self):
        return self.filter(status=AccountStatus.ACTIVE)

    def pending_verification(self):
        return self.filter(status=AccountStatus.PENDING_VERIFICATION)


class CustomUserManager(BaseUserManager):
    """
    Custom manager for the Sifo Drive User model.

    Phone number is the primary identifier (not username or email).
    Email is optional but unique when provided.
    """

    def _create_user(self, phone_number: str, password: str, **extra_fields):
        """
        Core user creation logic. Validates and normalises inputs.
        """
        if not phone_number:
            raise ValueError(_("A phone number is required to create a user."))

        # Normalize phone to E.164 format
        from apps.core.utils import normalize_phone_number
        normalized_phone = normalize_phone_number(phone_number)
        if not normalized_phone:
            raise ValueError(_("The provided phone number is invalid."))

        if "email" in extra_fields and extra_fields["email"]:
            extra_fields["email"] = self.normalize_email(extra_fields["email"])

        user = self.model(phone_number=normalized_phone, **extra_fields)
        user.set_password(password)
        user.full_clean()  # Run model-level validation
        user.save(using=self._db)
        return user

    def create_user(self, phone_number: str, password: str = None, **extra_fields):
        """Create and return a standard (non-staff) user."""
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        extra_fields.setdefault("role", UserRole.GUEST)
        extra_fields.setdefault("status", AccountStatus.PENDING_VERIFICATION)
        return self._create_user(phone_number, password, **extra_fields)

    def create_student(self, phone_number: str, password: str = None, **extra_fields):
        """Create an enrolled student. Student ID is generated post-save via signal."""
        extra_fields["role"] = UserRole.STUDENT
        return self.create_user(phone_number, password, **extra_fields)

    def create_tutor(self, phone_number: str, password: str = None, **extra_fields):
        """Create a tutor account (typically done by SYSTEM_ADMIN)."""
        extra_fields["role"] = UserRole.TUTOR
        extra_fields["status"] = AccountStatus.ACTIVE
        return self.create_user(phone_number, password, **extra_fields)

    def create_superuser(self, phone_number: str, password: str, **extra_fields):
        """Create a Django superuser (maps to SYSTEM_ADMIN role)."""
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields["role"] = UserRole.SYSTEM_ADMIN
        extra_fields["status"] = AccountStatus.ACTIVE

        if extra_fields.get("is_staff") is not True:
            raise ValueError(_("Superuser must have is_staff=True."))
        if extra_fields.get("is_superuser") is not True:
            raise ValueError(_("Superuser must have is_superuser=True."))

        return self._create_user(phone_number, password, **extra_fields)
