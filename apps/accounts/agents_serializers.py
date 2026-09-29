"""
apps/accounts/agents_serializers.py
===================================
Backward-compatible facade.
All serializers have moved to apps.accounts.serializers.
"""

from apps.accounts.serializers import (
    ServiceCommissionConfigSerializer,
    AgentCommissionSerializer,
    StaffUserListSerializer,
    StaffUserCreateSerializer,
    StaffUserUpdateSerializer,
    AgentPayoutSerializer,
    AgentOnboardClientSerializer,
    AgentFacilitateServiceSerializer,
)

__all__ = [
    "ServiceCommissionConfigSerializer",
    "AgentCommissionSerializer",
    "StaffUserListSerializer",
    "StaffUserCreateSerializer",
    "StaffUserUpdateSerializer",
    "AgentPayoutSerializer",
    "AgentOnboardClientSerializer",
    "AgentFacilitateServiceSerializer",
]
