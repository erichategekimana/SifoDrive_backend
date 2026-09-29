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
    # Profile
    "UserProfileView",
    "StudentProfileView",
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
    # Analytics
    "AdminPlatformAnalyticsView",
    "TIMEFRAME_PROFILES",
]
