"""
apps/accounts/views/__init__.py
==================================
Public re-export surface for the accounts views package.

All view classes remain importable from `apps.accounts.views` — existing
urls.py references are unchanged.

Domain layout:
  auth_views.py      → Registration, OTP, Login, Token, Consent views
  profile_views.py   → User self-service profile + student profile
  admin_views.py     → User management (System Admin & Training Admin)
  agent_views.py     → Agents & Staff management, commission configs, ledger & payouts
  analytics_views.py → Platform analytics hub
"""

# Authentication flows
from apps.accounts.views.auth_views import (
    GuestRegistrationView,
    StudentRegistrationView,
    GuestUpgradeView,
    LoginView,
    OTPRequestView,
    OTPVerifyView,
    AcceptTermsOfServiceView,
    AcceptPrivacyPolicyView,
)

# Profile self-service
from apps.accounts.views.profile_views import (
    UserProfileView,
    StudentProfileView,
    StudentEligibilityView,
)

# Admin user management
from apps.accounts.views.admin_views import (
    UserListView,
    AdminDashboardStatsView,
    AdminUserCreateView,
    AdminUserDetailView,
    AdminUserRoleUpdateView,
    AdminUserStatusUpdateView,
    AdminUserTutorAssignView,
)

# Agents & Staff management
from apps.accounts.views.agent_views import (
    StaffOverviewMetricsView,
    StaffListCreateView,
    StaffDetailView,
    ServiceCommissionConfigView,
    AgentCommissionsListView,
    AgentMonthlyPayoutView,
    AgentOnboardClientView,
    AgentFacilitateServiceView,
)

# Tutor / Instructor
from apps.accounts.views.tutor_views import (
    TutorStatsView,
    TutorProfileView,
    TutorStudentsListView,
)

# Enterprise / Driving School
from apps.accounts.views.enterprise_views import (
    EnterpriseStatsView,
    EnterpriseProfileView,
    EnterpriseStudentsListView,
    EnterpriseBulkEnrollView,
)

# Board Reviewer / Integrity Examiner
from apps.accounts.views.reviewer_views import (
    ReviewerStatsView,
    ReviewerProfileView,
    ReviewerQueueView,
    ReviewerCertifyView,
)

# Platform Analytics
from apps.accounts.views.analytics_views import (
    AdminPlatformAnalyticsView,
    TIMEFRAME_PROFILES,
)

__all__ = [
    # Auth
    "GuestRegistrationView",
    "StudentRegistrationView",
    "GuestUpgradeView",
    "LoginView",
    "OTPRequestView",
    "OTPVerifyView",
    "AcceptTermsOfServiceView",
    "AcceptPrivacyPolicyView",
    # Profile & Student
    "UserProfileView",
    "StudentProfileView",
    "StudentEligibilityView",
    # Admin
    "UserListView",
    "AdminDashboardStatsView",
    "AdminUserCreateView",
    "AdminUserDetailView",
    "AdminUserRoleUpdateView",
    "AdminUserStatusUpdateView",
    "AdminUserTutorAssignView",
    # Agents & Staff
    "StaffOverviewMetricsView",
    "StaffListCreateView",
    "StaffDetailView",
    "ServiceCommissionConfigView",
    "AgentCommissionsListView",
    "AgentMonthlyPayoutView",
    "AgentOnboardClientView",
    "AgentFacilitateServiceView",
    # Tutor
    "TutorStatsView",
    "TutorProfileView",
    "TutorStudentsListView",
    # Enterprise
    "EnterpriseStatsView",
    "EnterpriseProfileView",
    "EnterpriseStudentsListView",
    "EnterpriseBulkEnrollView",
    # Reviewer
    "ReviewerStatsView",
    "ReviewerProfileView",
    "ReviewerQueueView",
    "ReviewerCertifyView",
    # Analytics
    "AdminPlatformAnalyticsView",
    "TIMEFRAME_PROFILES",
]
