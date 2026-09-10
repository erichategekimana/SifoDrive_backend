"""
apps/audit/context.py
======================
Thread-local storage for the current HTTP request context.

The middleware writes into this store so that AuditLog.objects.create_log()
can pick up IP, user-agent, request-id, etc. even when the request object
is not explicitly passed down the call stack (e.g. from inside a Celery task
that was triggered by a request, or from deep inside a service method).

Usage:
    # In middleware (write):
    set_current_request_context(request)

    # In any service/model (read):
    ctx = get_current_request_context()
    ip  = ctx.get("ip_address")
"""

import threading
import uuid

_thread_local = threading.local()


def set_current_request_context(request) -> None:
    """
    Store the current request's audit-relevant metadata in thread-local.
    Called once per request by AuditLogMiddleware at the start of the cycle.
    """
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    ip = forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR", "")

    # Honour an incoming X-Request-ID, or mint a fresh one for tracing
    request_id = request.META.get("HTTP_X_REQUEST_ID") or str(uuid.uuid4())

    _thread_local.audit_context = {
        "ip_address":  ip or None,
        "user_agent":  request.META.get("HTTP_USER_AGENT", "")[:500],
        "request_id":  request_id,
        "http_method": request.method,
        "endpoint":    request.path[:300],
    }

    # Stamp the request itself so downstream code can read it without import
    request.audit_request_id = request_id


def get_current_request_context() -> dict:
    """Return the context dict for the current thread, or an empty dict."""
    return getattr(_thread_local, "audit_context", {})


def clear_current_request_context() -> None:
    """Clear thread-local state after the request completes."""
    if hasattr(_thread_local, "audit_context"):
        del _thread_local.audit_context
