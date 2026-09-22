"""
apps/audit/middleware.py
=========================
AuditLogMiddleware — two responsibilities:

1. CONTEXT INJECTION
   At the start of every request, write IP / user-agent / request-id /
   method / endpoint into thread-local storage so that AuditLog.objects.create_log()
   can access them without needing the request object passed explicitly.

2. AUTOMATIC SENSITIVE-PATH LOGGING
   After the response is returned, auto-create an AuditLog entry for any
   request that matches a sensitive path pattern AND is authenticated.
   This is the "catch-all" safety net — individual services still create
   their own specific log entries (NID_ACCESS, BOOKING_STATE, etc.).

Thread safety: each request runs in its own thread (Gunicorn gthread / uvicorn).
The thread-local is cleared after the response is sent.
"""

import logging

from .context import (
    clear_current_request_context,
    get_current_request_context,
    set_current_request_context,
)
from .models import AuditAction, AuditLog

logger = logging.getLogger("apps.audit")


# ---------------------------------------------------------------------------
# Sensitive path → action mapping
# Each tuple: (path_prefix, http_methods, AuditAction)
# Only authenticated requests on matching paths are auto-logged.
# ---------------------------------------------------------------------------

SENSITIVE_PATH_RULES: list[tuple[str, set[str], str]] = [
    # Admin user-list: every GET exposes a user directory
    ("/api/v1/auth/users/",          {"GET"},               AuditAction.NID_ACCESS),

    # Booking data — reading NID / applicant details
    ("/api/v1/booking/",            {"GET", "PATCH"},       AuditAction.BOOKING_ACCESSED),
    ("/api/v1/irembo/",             {"GET", "PATCH"},       AuditAction.BOOKING_ACCESSED),

    # Exam proctoring snapshots or flagging actions
    ("/api/v1/exams/",              {"POST", "PATCH"},      AuditAction.EXAM_STARTED),

    # Admin site login
    ("/admin/login/",               {"POST"},               AuditAction.ADMIN_LOGIN),
    ("/admin/logout/",              {"POST", "GET"},        AuditAction.ADMIN_LOGOUT),

    # System config endpoints
    ("/api/v1/auth/users/",         {"POST", "PATCH"},      AuditAction.SYSTEM_CONFIG),

    # LMS Curriculum & Content management (Training Admin / Content Staff)
    ("/api/v1/lms/courses/",        {"POST", "PATCH", "DELETE"}, AuditAction.CONTENT_PUBLISHED),
    ("/api/v1/lms/modules/",        {"POST", "PATCH", "DELETE"}, AuditAction.CONTENT_PUBLISHED),
    ("/api/v1/lms/lessons/",        {"POST", "PATCH", "DELETE"}, AuditAction.CONTENT_PUBLISHED),
    ("/api/v1/lms/questions/",      {"POST", "PATCH", "DELETE"}, AuditAction.QUESTION_CREATED),

    # Live Tutoring & Timetable sessions
    ("/api/v1/live-classes/",       {"POST", "PATCH", "DELETE"}, AuditAction.SYSTEM_CONFIG),
]

# HTTP status codes that are considered audit-worthy (skip redirects, assets)
LOGGABLE_STATUSES = {200, 201, 204, 400, 403, 404}


class AuditLogMiddleware:
    """
    WSGI middleware that injects request context and auto-logs sensitive paths.
    Position in MIDDLEWARE list: after SecurityMiddleware, before SessionMiddleware.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # ── 1. Inject context into thread-local ──────────────────────────────
        set_current_request_context(request)

        try:
            response = self.get_response(request)
        finally:
            # ── 3. Always clean up thread-local (even on exception) ──────────
            clear_current_request_context()

        # ── 2. Auto-log sensitive path hits ─────────────────────────────────
        self._auto_log(request, response)

        return response

    # -------------------------------------------------------------------------

    def _auto_log(self, request, response) -> None:
        """
        Create an AuditLog entry for sensitive API paths if:
          - The request path matches a rule
          - The HTTP method matches
          - The user is authenticated
          - The response status is in LOGGABLE_STATUSES
        """
        if response.status_code not in LOGGABLE_STATUSES:
            return

        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return

        path = request.path
        method = request.method

        for path_prefix, methods, action in SENSITIVE_PATH_RULES:
            if path.startswith(path_prefix) and method in methods:
                try:
                    AuditLog.objects.create_log(
                        action=action,
                        performed_by=request.user,
                        request=request,
                        context={
                            "auto_logged": True,
                            "response_status": response.status_code,
                        },
                    )
                except Exception as exc:
                    # Audit log failure must NEVER crash the application
                    logger.error(
                        "Auto-audit log failed | path=%s action=%s error=%s",
                        path,
                        action,
                        exc,
                        exc_info=True,
                    )
                break  # First matching rule wins

    # -------------------------------------------------------------------------

    @staticmethod
    def get_client_ip(request) -> str | None:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR") or None
