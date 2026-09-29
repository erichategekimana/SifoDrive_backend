"""
apps/accounts/agents_views.py
=============================
Backward-compatible facade.
All views have moved to apps.accounts.views.
"""

from apps.accounts.views import (
    StaffOverviewMetricsView,
    StaffListCreateView,
    StaffDetailView,
    ServiceCommissionConfigView,
    AgentCommissionsListView,
    AgentMonthlyPayoutView,
    AgentOnboardClientView,
    AgentFacilitateServiceView,
)

__all__ = [
    "StaffOverviewMetricsView",
    "StaffListCreateView",
    "StaffDetailView",
    "ServiceCommissionConfigView",
    "AgentCommissionsListView",
    "AgentMonthlyPayoutView",
    "AgentOnboardClientView",
    "AgentFacilitateServiceView",
]
