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
    AdminDashboardStatsView,
    AdminPlatformAnalyticsView,
    AdminUserCreateView,
    AdminUserDetailView,
    AdminUserRoleUpdateView,
    AdminUserStatusUpdateView,
    AdminUserTutorAssignView,
    AgentCommissionsListView,
    AgentFacilitateServiceView,
    AgentMonthlyPayoutView,
    AgentOnboardClientView,
    EnterpriseBulkEnrollView,
    EnterpriseProfileView,
    EnterpriseStatsView,
    EnterpriseStudentsListView,
    GuestRegistrationView,
    GuestUpgradeView,
    ActiveSessionsView,
    LoginView,
    OTPRequestView,
    OTPVerifyView,
    PasswordChangeView,
    ReviewerCertifyView,
    ReviewerProfileView,
    ReviewerQueueView,
    ReviewerStatsView,
    ServiceCommissionConfigView,
    StaffDetailView,
    StaffListCreateView,
    StaffOverviewMetricsView,
    StudentEligibilityView,
    StudentProfileView,
    StudentRegistrationView,
    TutorProfileView,
    TutorStatsView,
    TutorStudentsListView,
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
    # Authentication (Password Login — No OTP)
    # -------------------------------------------------------------------------
    path("login/", LoginView.as_view(), name="login"),

    # -------------------------------------------------------------------------
    # Account Upgrade (Guest → Student)
    # -------------------------------------------------------------------------
    path("upgrade/student/", GuestUpgradeView.as_view(), name="upgrade-to-student"),

    # -------------------------------------------------------------------------
    # OTP
    # -------------------------------------------------------------------------
    path("otp/request/", OTPRequestView.as_view(), name="otp-request"),
    path("otp/verify/", OTPVerifyView.as_view(), name="otp-verify"),
    path("password/change/", PasswordChangeView.as_view(), name="password-change"),
    path("sessions/", ActiveSessionsView.as_view(), name="active-sessions"),
    path("sessions/terminate/", ActiveSessionsView.as_view(), name="active-sessions-terminate"),

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
    # Profile & Student Hub
    # -------------------------------------------------------------------------
    path("me/", UserProfileView.as_view(), name="profile"),
    path("me/student-profile/", StudentProfileView.as_view(), name="student-profile"),
    path("me/student-profile/eligibility/", StudentEligibilityView.as_view(), name="student-eligibility"),

    # -------------------------------------------------------------------------
    # Tutor / Instructor Facilitation
    # -------------------------------------------------------------------------
    path("tutor/stats/", TutorStatsView.as_view(), name="tutor-stats"),
    path("tutor/profile/", TutorProfileView.as_view(), name="tutor-profile"),
    path("tutor/students/", TutorStudentsListView.as_view(), name="tutor-students"),

    # -------------------------------------------------------------------------
    # Enterprise / Driving School
    # -------------------------------------------------------------------------
    path("enterprise/stats/", EnterpriseStatsView.as_view(), name="enterprise-stats"),
    path("enterprise/profile/", EnterpriseProfileView.as_view(), name="enterprise-profile"),
    path("enterprise/students/", EnterpriseStudentsListView.as_view(), name="enterprise-students"),
    path("enterprise/students/bulk/", EnterpriseBulkEnrollView.as_view(), name="enterprise-bulk-students"),

    # -------------------------------------------------------------------------
    # Board Reviewer / Integrity Examiner
    # -------------------------------------------------------------------------
    path("reviewer/stats/", ReviewerStatsView.as_view(), name="reviewer-stats"),
    path("reviewer/profile/", ReviewerProfileView.as_view(), name="reviewer-profile"),
    path("reviewer/queue/", ReviewerQueueView.as_view(), name="reviewer-queue"),
    path("reviewer/certify/", ReviewerCertifyView.as_view(), name="reviewer-certify"),

    # -------------------------------------------------------------------------
    # Admin
    # -------------------------------------------------------------------------
    path("users/", UserListView.as_view(), name="user-list"),
    path("users/create/", AdminUserCreateView.as_view(), name="admin-user-create"),
    path("users/<uuid:user_id>/", AdminUserDetailView.as_view(), name="admin-user-detail"),
    path("users/<uuid:user_id>/role/", AdminUserRoleUpdateView.as_view(), name="admin-user-role"),
    path("users/<uuid:user_id>/status/", AdminUserStatusUpdateView.as_view(), name="admin-user-status"),
    path("users/<uuid:user_id>/tutor/", AdminUserTutorAssignView.as_view(), name="admin-user-tutor"),
    path("admin/stats/", AdminDashboardStatsView.as_view(), name="admin-stats"),
    path("admin/analytics/", AdminPlatformAnalyticsView.as_view(), name="admin-analytics"),

    # -------------------------------------------------------------------------
    # Agents & Staff Control Center
    # -------------------------------------------------------------------------
    path("staff/metrics/", StaffOverviewMetricsView.as_view(), name="staff-metrics"),
    path("staff/", StaffListCreateView.as_view(), name="staff-list-create"),
    path("staff/<uuid:staff_id>/", StaffDetailView.as_view(), name="staff-detail"),
    path("agent-commissions/rates/", ServiceCommissionConfigView.as_view(), name="commission-rates"),
    path("agent-commissions/", AgentCommissionsListView.as_view(), name="agent-commissions"),
    path("agent-commissions/payout/", AgentMonthlyPayoutView.as_view(), name="agent-payout"),
    path("agent/onboard-client/", AgentOnboardClientView.as_view(), name="agent-onboard-client"),
    path("agent/facilitate-service/", AgentFacilitateServiceView.as_view(), name="agent-facilitate-service"),
]
