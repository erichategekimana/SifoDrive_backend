"""
apps/accounts/analytics_views.py
=================================
Backward-compatible facade.
All views have moved to apps.accounts.views.
"""

from apps.accounts.views import (
    AdminPlatformAnalyticsView,
    TIMEFRAME_PROFILES,
)

__all__ = [
    "AdminPlatformAnalyticsView",
    "TIMEFRAME_PROFILES",
]
