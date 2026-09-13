"""
apps/notifications/urls.py
==========================
URL route declarations for notifications and administrative SMS auditing.
"""

from django.urls import path
from apps.notifications.views import (
    AdminBroadcastView,
    AdminGatewayStatusView,
    AdminSMSLogDetailView,
    AdminSMSLogListView,
    AdminSMSRetryView,
    AdminTemplateDetailView,
    AdminTemplateListCreateView,
    AdminTestSMSView,
    NotificationDetailView,
    NotificationListView,
    NotificationMarkAllReadView,
    NotificationMarkReadView,
    NotificationPreferenceView,
    NotificationUnreadCountView,
)

app_name = "notifications"

urlpatterns = [
    # ── Authenticated User Feed ─────────────────────────────────────────────
    path("", NotificationListView.as_view(), name="list"),
    path("unread-count/", NotificationUnreadCountView.as_view(), name="unread_count"),
    path("<uuid:pk>/", NotificationDetailView.as_view(), name="detail"),
    path("<uuid:pk>/read/", NotificationMarkReadView.as_view(), name="mark_read"),
    path("read-all/", NotificationMarkAllReadView.as_view(), name="mark_all_read"),
    path("preferences/", NotificationPreferenceView.as_view(), name="preferences"),

    # ── Admin SMS Audit & Templates ─────────────────────────────────────────
    path("admin/sms-logs/", AdminSMSLogListView.as_view(), name="admin_sms_logs"),
    path("admin/sms-logs/<uuid:pk>/", AdminSMSLogDetailView.as_view(), name="admin_sms_log_detail"),
    path("admin/sms-logs/<uuid:pk>/retry/", AdminSMSRetryView.as_view(), name="admin_sms_retry"),
    path("admin/templates/", AdminTemplateListCreateView.as_view(), name="admin_templates"),
    path("admin/templates/<uuid:pk>/", AdminTemplateDetailView.as_view(), name="admin_template_detail"),
    path("admin/broadcast/", AdminBroadcastView.as_view(), name="admin_broadcast"),
    path("admin/test-sms/", AdminTestSMSView.as_view(), name="admin_test_sms"),
    path("admin/gateway-status/", AdminGatewayStatusView.as_view(), name="admin_gateway_status"),
]
