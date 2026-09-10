"""
apps/accounts/urls.py
======================
Auth & account URL routes — all prefixed with /api/v1/auth/ in config/urls.py.

Complete endpoint map:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Registration
    POST  register/guest/            GuestRegistrationView
    POST  register/student/          StudentRegistrationView

  Account Upgrade
    POST  upgrade/student/           GuestUpgradeView

  OTP
    POST  otp/request/               OTPRequestView
    POST  otp/verify/                OTPVerifyView

  JWT Token Management
    POST  token/refresh/             TokenRefreshView     (simplejwt)
    POST  token/blacklist/           TokenBlacklistView   (simplejwt)

  Consent
    POST  consent/terms/             AcceptTermsOfServiceView
    POST  consent/privacy-policy/    AcceptPrivacyPolicyView

  Profile
    GET   me/                        UserProfileView
    PATCH me/                        UserProfileView
    GET   me/student-profile/        StudentProfileView
    PATCH me/student-profile/        StudentProfileView

  Admin
    GET   users/                     UserListView   (SYSTEM_ADMIN only)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

from django.urls import path
from rest_framework_simplejwt.views import TokenBlacklistView, TokenRefreshView

from .views import (
    AcceptPrivacyPolicyView,
    AcceptTermsOfServiceView,
    GuestRegistrationView,
    GuestUpgradeView,
    OTPRequestView,
    OTPVerifyView,
    StudentProfileView,
    StudentRegistrationView,
    UserListView,
    UserProfileView,
)

app_name = "accounts"

urlpatterns = [
    # -------------------------------------------------------------------------
    # Registration
    # -------------------------------------------------------------------------
    path("register/guest/", GuestRegistrationView.as_view(), name="register-guest"),
    path("register/student/", StudentRegistrationView.as_view(), name="register-student"),

    # -------------------------------------------------------------------------
    # Account Upgrade (Guest → Student)
    # -------------------------------------------------------------------------
    path("upgrade/student/", GuestUpgradeView.as_view(), name="upgrade-to-student"),

    # -------------------------------------------------------------------------
    # OTP
    # -------------------------------------------------------------------------
    path("otp/request/", OTPRequestView.as_view(), name="otp-request"),
    path("otp/verify/", OTPVerifyView.as_view(), name="otp-verify"),

    # -------------------------------------------------------------------------
    # JWT Token Management
    # -------------------------------------------------------------------------
    path("token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("token/blacklist/", TokenBlacklistView.as_view(), name="token-blacklist"),

    # -------------------------------------------------------------------------
    # Consent
    # -------------------------------------------------------------------------
    path("consent/terms/", AcceptTermsOfServiceView.as_view(), name="consent-terms"),
    path("consent/privacy-policy/", AcceptPrivacyPolicyView.as_view(), name="consent-privacy-policy"),

    # -------------------------------------------------------------------------
    # Profile
    # -------------------------------------------------------------------------
    path("me/", UserProfileView.as_view(), name="profile"),
    path("me/student-profile/", StudentProfileView.as_view(), name="student-profile"),

    # -------------------------------------------------------------------------
    # Admin
    # -------------------------------------------------------------------------
    path("users/", UserListView.as_view(), name="user-list"),
]
