"""
apps/core/permissions.py
=========================
Role-based DRF permission classes for Sifo Drive's 6-tier user system.

Usage in views:
    class MyView(generics.RetrieveAPIView):
        permission_classes = [IsStudent]

Composing permissions:
    permission_classes = [IsAuthenticated, IsStudentOrTutor]
"""

from rest_framework.permissions import BasePermission, IsAuthenticated

from apps.accounts.constants import UserRole


# ---------------------------------------------------------------------------
# Base Role Permission (inherit for all role checks)
# ---------------------------------------------------------------------------

class HasRole(BasePermission):
    """
    Generic role-based permission.
    Subclass and set `allowed_roles` tuple or override `has_permission`.
    """

    allowed_roles: tuple = ()
    message = "You do not have the required role to perform this action."

    def has_permission(self, request, view) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        if not self.allowed_roles:
            return True
        return request.user.role in self.allowed_roles


# ---------------------------------------------------------------------------
# Single-Role Permissions
# ---------------------------------------------------------------------------

class IsStudent(HasRole):
    """Allows access to enrolled Students only."""
    allowed_roles = (UserRole.STUDENT,)
    message = "Only enrolled students may access this resource."


class IsGuest(HasRole):
    """Allows access to Guest learners only."""
    allowed_roles = (UserRole.GUEST,)
    message = "Only guest accounts may access this resource."


class IsTutor(HasRole):
    """Allows access to Tutors / Facilitators only."""
    allowed_roles = (UserRole.TUTOR,)
    message = "Only tutors and facilitators may access this resource."


class IsEnterpriseAdmin(HasRole):
    """Allows access to Driving School (Enterprise) Admins only."""
    allowed_roles = (UserRole.ENTERPRISE_ADMIN,)
    message = "Only enterprise account administrators may access this resource."


class IsBoardReviewer(HasRole):
    """Allows access to Board Reviewers only."""
    allowed_roles = (UserRole.BOARD_REVIEWER,)
    message = "Only board reviewers may access this resource."


class IsSystemAdmin(HasRole):
    """Allows access to System Administrators only."""
    allowed_roles = (UserRole.SYSTEM_ADMIN,)
    message = "System administrator privileges are required."


# ---------------------------------------------------------------------------
# Multi-Role Composite Permissions
# ---------------------------------------------------------------------------

class IsStudentOrGuest(HasRole):
    """Students and Guests — general learner access."""
    allowed_roles = (UserRole.STUDENT, UserRole.GUEST)


class IsStudentOrTutor(HasRole):
    """Students and Tutors — for shared learning resources."""
    allowed_roles = (UserRole.STUDENT, UserRole.TUTOR)


class IsStaff(HasRole):
    """Tutors, Board Reviewers, and System Admins — internal staff."""
    allowed_roles = (
        UserRole.TUTOR,
        UserRole.BOARD_REVIEWER,
        UserRole.SYSTEM_ADMIN,
    )


class IsAdminLevel(HasRole):
    """Enterprise Admins, Board Reviewers, and System Admins."""
    allowed_roles = (
        UserRole.ENTERPRISE_ADMIN,
        UserRole.BOARD_REVIEWER,
        UserRole.SYSTEM_ADMIN,
    )


class IsAnyAuthenticatedRole(HasRole):
    """Any authenticated user regardless of role."""
    allowed_roles = tuple(role.value for role in UserRole)


# ---------------------------------------------------------------------------
# Object-Level Permissions
# ---------------------------------------------------------------------------

class IsOwnerOrSystemAdmin(BasePermission):
    """
    Object-level permission: only the record's owner or a SYSTEM_ADMIN
    may read or modify it.

    Requires the model to have an `owner` or `user` field.
    """

    message = "You do not have permission to access this record."

    def has_object_permission(self, request, view, obj) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.role == UserRole.SYSTEM_ADMIN:
            return True
        # Check common ownership field names
        owner = getattr(obj, "owner", None) or getattr(obj, "user", None) or getattr(obj, "student", None)
        return owner == request.user


class IsSameUserOrAdmin(BasePermission):
    """
    Allows a user to access their own profile, or a SYSTEM_ADMIN to access anyone's.
    """

    def has_object_permission(self, request, view, obj) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.role == UserRole.SYSTEM_ADMIN:
            return True
        return obj == request.user


# ---------------------------------------------------------------------------
# Consent Gate Permissions
# ---------------------------------------------------------------------------

class HasAcceptedTermsOfService(BasePermission):
    """
    Blocks any authenticated user who has not yet accepted the Terms of Service.

    This permission is automatically satisfied for users registered after
    v3.0 (TOS acceptance is required at registration). It acts as a safety
    net for legacy or admin-created accounts.

    Returns HTTP 403 with code 'terms_not_accepted'.
    """

    message = {
        "code": "terms_not_accepted",
        "message": (
            "You must accept the Terms of Service before accessing this feature. "
            "Please review and accept at /api/v1/auth/consent/terms/."
        ),
    }

    def has_permission(self, request, view) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.terms_of_service_accepted


class HasAcceptedPrivacyPolicy(BasePermission):
    """
    Blocks access to endpoints that collect, store, or process PII
    unless the user has explicitly accepted the Privacy Policy.

    Rwanda Law No 058/2021, Articles 6 & 17:
      'Affirmative, informed, unambiguous consent required before
       collecting biometrics or government IDs.'

    Usage on identity-collecting endpoints (exam start, Irembo booking):
        permission_classes = [IsAuthenticated, HasAcceptedPrivacyPolicy]

    Returns HTTP 403 with code 'privacy_policy_required' so the frontend
    can display the privacy policy modal and prompt re-submission.
    """

    message = {
        "code": "privacy_policy_required",
        "message": (
            "This action requires your consent to our Privacy Policy. "
            "Please review and accept at /api/v1/auth/consent/privacy-policy/."
        ),
    }

    def has_permission(self, request, view) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.privacy_policy_accepted
