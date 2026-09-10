"""
apps/audit/urls.py
===================
Audit log read-only API routes. Prefixed with /api/v1/audit/ in config/urls.py.

Endpoints:
  GET  logs/                   → AuditLogListView        (paginated + filtered)
  GET  logs/<uuid>/            → AuditLogDetailView      (single record + hash status)
  GET  users/<user_id>/        → UserAuditTrailView      (per-user full timeline)
  GET  critical/               → CriticalEventsView      (HIGH+CRITICAL last 24h)
  GET  integrity/              → IntegrityStatsView      (quick hash verification)
"""

from django.urls import path

from .views import (
    AuditLogDetailView,
    AuditLogListView,
    CriticalEventsView,
    IntegrityStatsView,
    UserAuditTrailView,
)

app_name = "audit"

urlpatterns = [
    path("logs/",                  AuditLogListView.as_view(),    name="log-list"),
    path("logs/<uuid:id>/",        AuditLogDetailView.as_view(),  name="log-detail"),
    path("users/<uuid:user_id>/",  UserAuditTrailView.as_view(),  name="user-trail"),
    path("critical/",              CriticalEventsView.as_view(),  name="critical"),
    path("integrity/",             IntegrityStatsView.as_view(),  name="integrity"),
]
