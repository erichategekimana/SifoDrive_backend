"""
apps/accounts/agents_services.py
================================
Backward-compatible facade.
All services have moved to apps.accounts.services.
"""

from apps.accounts.services import AgentService, DEFAULT_COMMISSIONS

__all__ = [
    "AgentService",
    "DEFAULT_COMMISSIONS",
]
