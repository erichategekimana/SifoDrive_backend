"""
apps/accounts/models/__init__.py
================================
Facade exposing all accounts models.
"""

from apps.accounts.models.user import User
from apps.accounts.models.otp import OTPVerification
from apps.accounts.models.student import StudentProfile
from apps.accounts.models.agent import (
    AgentCommission,
    AgentProfile,
    ServiceCommissionConfig,
)

__all__ = [
    "User",
    "OTPVerification",
    "StudentProfile",
    "AgentProfile",
    "ServiceCommissionConfig",
    "AgentCommission",
]
