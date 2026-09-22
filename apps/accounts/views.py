"""
apps/accounts/views.py
=======================
Auth & account API views.

Views are deliberately thin — all business logic lives in services.py.
Each view's docstring describes the full request/response contract.

Auth flow summary
─────────────────
  GUEST REGISTRATION
    POST /auth/register/guest/       → creates account, sends OTP
    POST /auth/otp/verify/           → verifies phone, returns JWT

  STUDENT REGISTRATION
    POST /auth/register/student/     → creates account, sends OTP
    POST /auth/otp/verify/           → verifies phone, returns JWT

  GUEST → STUDENT UPGRADE
    POST /auth/upgrade/student/      → promotes guest, accept privacy policy

  RETURNING USER LOGIN
    POST /auth/otp/request/          → sends login OTP
    POST /auth/otp/verify/           → verifies, returns JWT

  TOKEN MANAGEMENT
    POST /auth/token/refresh/        → refresh access token
    POST /auth/token/blacklist/      → logout (invalidates refresh token)

  CONSENT ENDPOINTS
    POST /auth/consent/terms/        → accept Terms of Service
    POST /auth/consent/privacy-policy/ → accept Privacy Policy (guest lazy flow)

  PROFILE
    GET  /auth/me/                   → authenticated user's profile
    PATCH /auth/me/                  → update profile
    GET  /auth/me/student-profile/   → student extended profile
    PATCH /auth/me/student-profile/  → update student extended profile

  ADMIN
    GET  /auth/users/                → list all users (SYSTEM_ADMIN only)
"""

import logging

from django.contrib.auth import get_user_model
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.exceptions import PermissionDeniedException
from apps.core.mixins import SuccessResponseMixin
from apps.core.permissions import IsSystemAdmin, IsSameUserOrAdmin, IsTrainingAdminOrAbove

from .serializers import (
    AcceptPrivacyPolicySerializer,
    AcceptTermsOfServiceSerializer,
    AdminCreateUserSerializer,
    AdminUserDetailSerializer,
    AdminUserListSerializer,
    AdminUserRoleUpdateSerializer,
    AdminUserStatusUpdateSerializer,
    GuestRegistrationSerializer,
    GuestUpgradeSerializer,
    LoginSerializer,
    OTPRequestSerializer,
    OTPVerifySerializer,
    StudentProfileSerializer,
    StudentRegistrationSerializer,
    UserProfileSerializer,
)
from .services import AuthService, StudentService, UserService

User = get_user_model()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _build_token_response(user: User) -> dict:
    """Create a JWT pair + user summary dict for all auth success responses."""
    refresh = RefreshToken.for_user(user)
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
        "user": {
            "id": str(user.id),
            "role": user.role,
            "full_name": user.full_name,
            "status": user.status,
            "student_id": user.student_id,
            "terms_accepted": user.terms_of_service_accepted,
            "privacy_accepted": user.privacy_policy_accepted,
        },
    }


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

class GuestRegistrationView(SuccessResponseMixin, generics.CreateAPIView):
    """
    POST /api/v1/auth/register/guest/

    Register a new free Guest account.

    Required fields:
      - first_name, last_name
      - phone_number
      - password (min 8 chars)
      - terms_of_service_accepted: true

    On success (HTTP 201):
      - Account created (status: PENDING_VERIFICATION)
      - OTP SMS sent to the provided phone number
      - Returns the phone number so the client knows where to direct the user

    Next step: POST /auth/otp/verify/ with purpose=REGISTRATION
    """

    permission_classes = [permissions.AllowAny]
    serializer_class = GuestRegistrationSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        # Trigger OTP after account creation
        AuthService.request_otp(user.phone_number, purpose="REGISTRATION")

        return self.created_response(
            data={"phone_number": user.phone_number},
            message=(
                "Account created. An OTP has been sent to your phone. "
                "Please verify to activate your account."
            ),
        )


class StudentRegistrationView(SuccessResponseMixin, generics.CreateAPIView):
    """
    POST /api/v1/auth/register/student/

    Register as an enrolled student (formal learner).

    Required fields:
      - first_name, last_name
      - phone_number
      - password (min 8 chars)
      - terms_of_service_accepted: true
      - privacy_policy_accepted: true  ← required upfront for students

    Optional:
      - email

    Fields completed AFTER registration + payment:
      - date_of_birth, profile_photo, national_id (Indangamuntu)
      - Student ID is auto-generated after tuition payment is confirmed

    On success (HTTP 201):
      - Account created (status: PENDING_VERIFICATION)
      - OTP SMS sent to the provided phone number

    Next step: POST /auth/otp/verify/ with purpose=REGISTRATION
    """

    permission_classes = [permissions.AllowAny]
    serializer_class = StudentRegistrationSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        AuthService.request_otp(user.phone_number, purpose="REGISTRATION")

        return self.created_response(
            data={"phone_number": user.phone_number},
            message=(
                "Student account created. An OTP has been sent to your phone. "
                "Please verify to activate your account, then proceed to payment."
            ),
        )


# ---------------------------------------------------------------------------
# Guest → Student Upgrade
# ---------------------------------------------------------------------------

class GuestUpgradeView(SuccessResponseMixin, APIView):
    """
    POST /api/v1/auth/upgrade/student/

    Allows a verified GUEST to upgrade their account to STUDENT.

    The guest must accept the Privacy Policy at this point (if not already done)
    since upgrading initiates the identity-collection and payment enrollment flow.

    Required:
      - Authenticated as GUEST with ACTIVE status
      - privacy_policy_accepted: true

    On success (HTTP 200):
      - role changed GUEST → STUDENT
      - StudentProfile created
      - Fresh JWT tokens returned with updated role claim
      - Client should redirect to the enrollment completion flow
        (payment, date of birth, photo, national ID)
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        user = request.user

        if user.role != "GUEST":
            raise PermissionDeniedException(
                "Only guest accounts can be upgraded. Your current role is: "
                + user.get_role_display() if hasattr(user, "get_role_display") else user.role
            )

        serializer = GuestUpgradeSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)

        # Record privacy policy consent (may already be accepted — idempotent)
        user.accept_privacy_policy()

        # Perform the role promotion
        user = StudentService.upgrade_guest_to_student(user)

        return SuccessResponseMixin().success_response(
            data=_build_token_response(user),
            message=(
                "Your account has been upgraded to Student. "
                "Please complete your enrollment (payment, profile details)."
            ),
        )


# ---------------------------------------------------------------------------
# Password Login Flow (No OTP Required)
# ---------------------------------------------------------------------------

class LoginView(SuccessResponseMixin, APIView):
    """
    POST /api/v1/auth/login/

    Authenticate a user with phone number and password.
    Returns JWT token pair + user summary envelope on success.
    No OTP is required for login.
    """

    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = AuthService.authenticate_by_password(
            phone_number=serializer.validated_data["phone_number"],
            password=serializer.validated_data["password"],
        )

        return self.success_response(
            data=_build_token_response(user),
            message="Login successful.",
        )


# ---------------------------------------------------------------------------
# OTP Flow
# ---------------------------------------------------------------------------

class OTPRequestView(SuccessResponseMixin, APIView):
    """
    POST /api/v1/auth/otp/request/

    Request a new OTP code for login or verification.

    Body:
      - phone_number: string
      - purpose: "LOGIN" | "REGISTRATION" | "PASSWORD_RESET" (default: "LOGIN")

    Rate-limited to 5 requests per hour per phone number per purpose.
    """

    permission_classes = [permissions.AllowAny]
    throttle_scope = "otp"

    def post(self, request, *args, **kwargs):
        serializer = OTPRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        AuthService.request_otp(
            phone_number=serializer.validated_data["phone_number"],
            purpose=serializer.validated_data["purpose"],
        )
        return self.success_response(
            message=f"OTP sent to your phone. It expires in {request.settings.OTP_EXPIRY_MINUTES if hasattr(request, 'settings') else 10} minutes."
        )


class OTPVerifyView(SuccessResponseMixin, APIView):
    """
    POST /api/v1/auth/otp/verify/

    Verify an OTP and receive JWT tokens on success.

    Body:
      - phone_number: string
      - otp_code: string (6 digits)
      - purpose: "LOGIN" | "REGISTRATION" (default: "LOGIN")

    On success (HTTP 200):
      Returns:
        - access: JWT access token
        - refresh: JWT refresh token
        - user: { id, role, full_name, status, student_id, terms_accepted, privacy_accepted }

    The `terms_accepted` and `privacy_accepted` flags in the response tell the
    frontend whether to show consent modals before proceeding.
    """

    permission_classes = [permissions.AllowAny]
    throttle_scope = "otp"

    def post(self, request, *args, **kwargs):
        serializer = OTPVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = AuthService.verify_otp(
            phone_number=serializer.validated_data["phone_number"],
            raw_otp=serializer.validated_data["otp_code"],
            purpose=serializer.validated_data["purpose"],
        )

        return self.success_response(
            data=_build_token_response(user),
            message="Phone verified successfully.",
        )


# ---------------------------------------------------------------------------
# Consent Endpoints
# ---------------------------------------------------------------------------

class AcceptTermsOfServiceView(SuccessResponseMixin, APIView):
    """
    POST /api/v1/auth/consent/terms/

    Explicit Terms of Service acceptance.
    Used for accounts that were created before TOS tracking was introduced,
    or for re-acceptance flows (e.g., after a TOS update).

    Body: { "accepted": true }
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = AcceptTermsOfServiceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        request.user.accept_terms_of_service()
        return self.success_response(
            message="Terms of Service accepted. Thank you.",
        )


class AcceptPrivacyPolicyView(SuccessResponseMixin, APIView):
    """
    POST /api/v1/auth/consent/privacy-policy/

    Lazy Privacy Policy acceptance for guest users.

    Called by the frontend when a guest clicks 'Accept & Continue' on the
    privacy policy modal shown before an identity-collecting action
    (e.g., starting an exam or submitting an Irembo booking).

    Body: { "accepted": true }

    On success:
      - privacy_policy_accepted set to True on the user record
      - The client should re-attempt the original blocked request
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = AcceptPrivacyPolicySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        request.user.accept_privacy_policy()
        return self.success_response(
            message="Privacy Policy accepted. You may now proceed.",
        )


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

class UserProfileView(SuccessResponseMixin, generics.RetrieveUpdateAPIView):
    """
    GET  /api/v1/auth/me/   — Retrieve authenticated user's profile
    PATCH /api/v1/auth/me/  — Update profile fields
                              (updateable: first_name, last_name, email, profile_photo, date_of_birth)
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserProfileSerializer

    def get_object(self):
        return self.request.user

    def retrieve(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_object())
        return self.success_response(data=serializer.data)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return self.success_response(data=serializer.data, message="Profile updated.")


class StudentProfileView(SuccessResponseMixin, generics.RetrieveUpdateAPIView):
    """
    GET  /api/v1/auth/me/student-profile/
    PATCH /api/v1/auth/me/student-profile/

    Student-specific extended profile: preferred language, license category, streak.
    Only accessible to authenticated users with a StudentProfile (STUDENT role).
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = StudentProfileSerializer

    def get_object(self):
        try:
            return self.request.user.student_profile
        except AttributeError:
            from rest_framework.exceptions import NotFound
            raise NotFound("Student profile not found. Are you registered as a student?")

    def retrieve(self, request, *args, **kwargs):
        return self.success_response(data=self.get_serializer(self.get_object()).data)

    def update(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_object(), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return self.success_response(data=serializer.data, message="Student profile updated.")


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------

class UserListView(SuccessResponseMixin, generics.ListAPIView):
    """
    GET /api/v1/auth/users/

    System Admin only — paginated list of all users.
    Supports filtering by role / status and searching by phone / name / student_id.
    """

    permission_classes = [IsSystemAdmin]
    serializer_class = AdminUserListSerializer
    filterset_fields = ["role", "status"]
    search_fields = ["phone_number", "first_name", "last_name", "email", "student_id"]
    ordering_fields = ["created_at", "last_name", "role", "status"]
    ordering = ["-created_at"]

    def get_queryset(self):
        return User.objects.all().select_related("assigned_tutor").prefetch_related("enrolled_cohorts")


class AdminDashboardStatsView(SuccessResponseMixin, APIView):
    """
    GET /api/v1/auth/admin/stats/

    Command Center basic platform metrics for System Admin:
    - total_registered_users
    - total_booking_orders
    - enrolled_students
    - total_graduated_students
    - lms_courses
    """

    permission_classes = [IsTrainingAdminOrAbove]

    def get(self, request, *args, **kwargs):
        from apps.accounts.constants import UserRole
        from apps.accounts.models import User
        from apps.booking.models import BookingApplication, BookingState
        from apps.examinations.models import ExamSession
        from apps.lms.models import Course

        total_registered_users = User.objects.count()
        enrolled_students = User.objects.filter(role=UserRole.STUDENT).count()
        total_booking_orders = BookingApplication.objects.count()
        lms_courses = Course.objects.filter(is_deleted=False).count()

        # Graduated students: passed official exam or completed driving test booking
        graduated_from_exams = ExamSession.objects.filter(passed=True).values("student").distinct().count()
        completed_bookings = BookingApplication.objects.filter(state=BookingState.COMPLETED).values("applicant").distinct().count()
        total_graduated_students = max(graduated_from_exams, completed_bookings)

        return self.success_response(
            data={
                "total_registered_users": total_registered_users,
                "total_booking_orders": total_booking_orders,
                "enrolled_students": enrolled_students,
                "total_graduated_students": total_graduated_students,
                "lms_courses": lms_courses,
            }
        )


class AdminUserCreateView(SuccessResponseMixin, generics.CreateAPIView):
    """
    POST /api/v1/auth/users/create/

    System Admin only. Creates accounts for other roles (TUTOR, ENTERPRISE_ADMIN, etc.).
    STRICT PRIVILEGE BOUNDARY: Cannot create another SYSTEM_ADMIN.
    """

    permission_classes = [IsSystemAdmin]
    serializer_class = AdminCreateUserSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return self.success_response(
            data=AdminUserDetailSerializer(user).data,
            message=f"Account created successfully for {user.full_name} ({user.role}).",
            status_code=status.HTTP_201_CREATED,
        )


class AdminUserDetailView(SuccessResponseMixin, generics.RetrieveAPIView):
    """
    GET /api/v1/auth/users/<uuid:user_id>/

    System Admin only — inspect user profile, credentials metadata, and consent status.
    """

    permission_classes = [IsSystemAdmin]
    serializer_class = AdminUserDetailSerializer
    queryset = User.objects.all().select_related("assigned_tutor")
    lookup_field = "id"
    lookup_url_kwarg = "user_id"

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        return self.success_response(data=self.get_serializer(instance).data)


class AdminUserRoleUpdateView(SuccessResponseMixin, APIView):
    """
    POST /api/v1/auth/users/<uuid:user_id>/role/

    System Admin only — updates user's role.
    STRICT PRIVILEGE BOUNDARY:
    - Cannot promote anyone to SYSTEM_ADMIN.
    - Cannot alter role of existing SYSTEM_ADMIN accounts.
    """

    permission_classes = [IsSystemAdmin]

    def post(self, request, user_id, *args, **kwargs):
        from rest_framework.exceptions import ValidationError, NotFound
        from apps.accounts.constants import UserRole

        try:
            target_user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            raise NotFound("User not found.")

        if target_user.role == UserRole.SYSTEM_ADMIN:
            raise ValidationError("Role of SYSTEM_ADMIN accounts cannot be modified via portal.")

        serializer = AdminUserRoleUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_role = serializer.validated_data["role"]

        user = UserService.promote_to_role(
            user=target_user,
            new_role=new_role,
            promoted_by=request.user,
        )

        return self.success_response(
            data=AdminUserDetailSerializer(user).data,
            message=f"User role updated to {user.role}.",
        )


class AdminUserStatusUpdateView(SuccessResponseMixin, APIView):
    """
    POST /api/v1/auth/users/<uuid:user_id>/status/

    System Admin only — activate, deactivate, suspend, or blacklist user account.
    STRICT PRIVILEGE BOUNDARY:
    - Cannot deactivate, suspend, or blacklist a SYSTEM_ADMIN account.
    """

    permission_classes = [IsSystemAdmin]

    def post(self, request, user_id, *args, **kwargs):
        from rest_framework.exceptions import ValidationError, NotFound
        from apps.accounts.constants import UserRole

        try:
            target_user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            raise NotFound("User not found.")

        if target_user.role == UserRole.SYSTEM_ADMIN and target_user != request.user:
            raise ValidationError("Status of other SYSTEM_ADMIN accounts cannot be altered.")

        serializer = AdminUserStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_status = serializer.validated_data["status"]
        reason = serializer.validated_data.get("reason", "")

        if new_status == AccountStatus.ACTIVE:
            target_user.activate()
        elif new_status == AccountStatus.DEACTIVATED:
            target_user.deactivate()
        elif new_status == AccountStatus.SUSPENDED:
            target_user.suspend()
        elif new_status == AccountStatus.BLACKLISTED:
            target_user.blacklist()

        logger.info(
            "User status changed | target=%s status=%s reason=%s by=%s",
            str(target_user.id)[:8],
            new_status,
            reason,
            str(request.user.id)[:8],
        )

        return self.success_response(
            data=AdminUserDetailSerializer(target_user).data,
            message=f"User account status changed to {target_user.status}.",
        )

