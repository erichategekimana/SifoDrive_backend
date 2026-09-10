"""
Sifo Drive — Master URL Configuration
=======================================
All API routes are versioned under /api/v1/.
Schema documentation is served at /api/schema/
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

# ---------------------------------------------------------------------------
# Admin Site Customization
# ---------------------------------------------------------------------------
admin.site.site_header = "Sifo Drive Administration"
admin.site.site_title = "Sifo Drive Admin Portal"
admin.site.index_title = "Welcome to Sifo Drive Admin"


# ---------------------------------------------------------------------------
# API v1 URL Patterns
# ---------------------------------------------------------------------------
api_v1_patterns = [
    # Auth & Accounts
    path("auth/", include("apps.accounts.urls", namespace="accounts")),

    # Learning Management System
    path("lms/", include("apps.lms.urls", namespace="lms")),

    # Examination Engine
    path("exams/", include("apps.examinations.urls", namespace="examinations")),

    # Live Classes (Google Meet scheduling)
    path("live-classes/", include("apps.live_classes.urls", namespace="live_classes")),

    # Irembo Booking Concierge
    path("irembo/", include("apps.irembo.urls", namespace="irembo")),

    # Mobile Money Payments
    path("payments/", include("apps.payments.urls", namespace="payments")),

    # SMS Notifications
    path("notifications/", include("apps.notifications.urls", namespace="notifications")),

    # Audit Logs (read-only — SYSTEM_ADMIN and BOARD_REVIEWER only)
    path("audit/", include("apps.audit.urls", namespace="audit")),
]


# ---------------------------------------------------------------------------
# Root URL Patterns
# ---------------------------------------------------------------------------
urlpatterns = [
    # Django Admin
    path("admin/", admin.site.urls),

    # API v1 — All application endpoints
    path("api/v1/", include((api_v1_patterns, "api_v1"))),

    # API Schema (OpenAPI 3.0)
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),

    # Interactive API Docs
    path("api/docs/swagger/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/docs/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]


# ---------------------------------------------------------------------------
# Development Extras (Debug Toolbar + Static Media serving)
# ---------------------------------------------------------------------------
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

    try:
        import debug_toolbar
        urlpatterns = [
            path("__debug__/", include(debug_toolbar.urls)),
        ] + urlpatterns
    except ImportError:
        pass
