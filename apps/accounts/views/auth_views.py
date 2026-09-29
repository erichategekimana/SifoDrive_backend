"""
apps/accounts/views/auth_views.py
===================================
Authentication flow views: registration, OTP, login, token management, consent.

Endpoints:
  POST /auth/register/guest/       → GuestRegistrationView
  POST /auth/register/student/     → StudentRegistrationView
  POST /auth/upgrade/student/      → GuestUpgradeView
  POST /auth/login/                → LoginView
  POST /auth/otp/request/          → OTPRequestView
  POST /auth/otp/verify/           → OTPVerifyView
  POST /auth/consent/terms/        → AcceptTermsOfServiceView
  POST /auth/consent/privacy-policy/ → AcceptPrivacyPolicyView
"""

import logging

from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.exceptions import PermissionDeniedException
from apps.core.mixins import SuccessResponseMixin

from apps.accounts.serializers import (
    AcceptPrivacyPolicySerializer,
    AcceptTermsOfServiceSerializer,
    GuestRegistrationSerializer,
    GuestUpgradeSerializer,
    LoginSerializer,
    OTPRequestSerializer,
    OTPVerifySerializer,
    StudentRegistrationSerializer,
)
from apps.accounts.services import AuthService, StudentService

logger = logging.getLogger(__name__)


def _build_token_response(user) -> dict:
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


# ===========================================================================
# REGISTRATION
# ===========================================================================

class GuestRegistrationView(SuccessResponseMixin, generics.CreateAPIView):
    """POST /api/v1/auth/register/guest/ — Register a new free Guest account."""
    permission_classes = [permissions.AllowAny]
    serializer_class = GuestRegistrationSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        AuthService.request_otp(user.phone_number, purpose="REGISTRATION")
        return self.created_response(
            data={"phone_number": user.phone_number},
            message=(
                "Account created. An OTP has been sent to your phone. "
                "Please verify to activate your account."
            ),
        )


class StudentRegistrationView(SuccessResponseMixin, generics.CreateAPIView):
    """POST /api/v1/auth/register/student/ — Register as an enrolled student."""
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


# ===========================================================================
# GUEST → STUDENT UPGRADE
# ===========================================================================

class GuestUpgradeView(SuccessResponseMixin, APIView):
    """POST /api/v1/auth/upgrade/student/ — Promote a verified GUEST to STUDENT."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        user = request.user
        if user.role != "GUEST":
            raise PermissionDeniedException(
                "Only guest accounts can be upgraded. Your current role is: "
                + (user.get_role_display() if hasattr(user, "get_role_display") else user.role)
            )
        serializer = GuestUpgradeSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user.accept_privacy_policy()
        user = StudentService.upgrade_guest_to_student(user)
        return self.success_response(
            data=_build_token_response(user),
            message=(
                "Your account has been upgraded to Student. "
                "Please complete your enrollment (payment, profile details)."
            ),
        )


# ===========================================================================
# LOGIN
# ===========================================================================

class LoginView(SuccessResponseMixin, APIView):
    """POST /api/v1/auth/login/ — Authenticate with phone + password, returns JWT pair."""
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = AuthService.authenticate_by_password(
            phone_number=serializer.validated_data["phone_number"],
            password=serializer.validated_data["password"],
        )
        return self.success_response(data=_build_token_response(user), message="Login successful.")


# ===========================================================================
# OTP FLOW
# ===========================================================================

class OTPRequestView(SuccessResponseMixin, APIView):
    """POST /api/v1/auth/otp/request/ — Request a new OTP for login or verification."""
    permission_classes = [permissions.AllowAny]
    throttle_scope = "otp"

    def post(self, request, *args, **kwargs):
        serializer = OTPRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        AuthService.request_otp(
            phone_number=serializer.validated_data["phone_number"],
            purpose=serializer.validated_data["purpose"],
        )
        return self.success_response(message="OTP sent to your phone. It expires in 10 minutes.")


class OTPVerifyView(SuccessResponseMixin, APIView):
    """POST /api/v1/auth/otp/verify/ — Verify an OTP and receive JWT tokens."""
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


# ===========================================================================
# CONSENT
# ===========================================================================

class AcceptTermsOfServiceView(SuccessResponseMixin, APIView):
    """POST /api/v1/auth/consent/terms/ — Explicit Terms of Service acceptance."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = AcceptTermsOfServiceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        request.user.accept_terms_of_service()
        return self.success_response(message="Terms of Service accepted. Thank you.")


class AcceptPrivacyPolicyView(SuccessResponseMixin, APIView):
    """POST /api/v1/auth/consent/privacy-policy/ — Lazy Privacy Policy acceptance for guests."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = AcceptPrivacyPolicySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        request.user.accept_privacy_policy()
        return self.success_response(message="Privacy Policy accepted. You may now proceed.")
