"""
apps/core/pagination.py
========================
Pagination classes for all Sifo Drive list endpoints.

Classes:
  StandardResultsPagination — 20 items/page, max 100 (default for all lists)
  LargeBatchPagination      — 100 items/page, max 500 (admin exports, reports)
  CursorBasedPagination     — cursor-based, for real-time feeds (notifications, audit log)

All paginators return the same response envelope:
    {
        "success":      true,
        "count":        150,        ← total items across all pages
        "total_pages":  8,
        "current_page": 1,
        "next":         "https://...",
        "previous":     null,
        "results":      [...]
    }
"""

from rest_framework.pagination import (
    CursorPagination,
    PageNumberPagination,
)
from rest_framework.response import Response


# ---------------------------------------------------------------------------
# Base Mixin — shared envelope logic
# ---------------------------------------------------------------------------

class _EnvelopeMixin:
    """Shared get_paginated_response() and OpenAPI schema for all paginators."""

    def get_paginated_response(self, data) -> Response:
        return Response(self._build_envelope(data))

    def _build_envelope(self, data) -> dict:
        payload: dict = {
            "success": True,
            "results": data,
        }
        # Page-number paginators have count / num_pages / page.number
        if hasattr(self, "page") and self.page is not None:
            payload["count"]        = self.page.paginator.count
            payload["total_pages"]  = self.page.paginator.num_pages
            payload["current_page"] = self.page.number
        # All paginators have next/previous links
        payload["next"]     = self.get_next_link()
        payload["previous"] = self.get_previous_link()
        return payload

    def get_paginated_response_schema(self, schema) -> dict:
        return {
            "type": "object",
            "required": ["success", "count", "results"],
            "properties": {
                "success":      {"type": "boolean", "example": True},
                "count":        {"type": "integer",  "example": 150},
                "total_pages":  {"type": "integer",  "example": 8},
                "current_page": {"type": "integer",  "example": 1},
                "next":         {"type": "string",   "nullable": True, "example": "https://api.sifodrive.rw/api/v1/.../?page=2"},
                "previous":     {"type": "string",   "nullable": True, "example": None},
                "results":      schema,
            },
        }


# ---------------------------------------------------------------------------
# StandardResultsPagination (default)
# ---------------------------------------------------------------------------

class StandardResultsPagination(_EnvelopeMixin, PageNumberPagination):
    """
    Default paginator for all list views.

    Defaults: 20 items / page
    Client can override with: ?page_size=50 (max 100)
    Navigate with: ?page=2
    """

    page_size              = 20
    page_size_query_param  = "page_size"
    max_page_size          = 100
    page_query_param       = "page"


# ---------------------------------------------------------------------------
# LargeBatchPagination (admin / export views)
# ---------------------------------------------------------------------------

class LargeBatchPagination(_EnvelopeMixin, PageNumberPagination):
    """
    High-volume paginator for admin-only list views and data exports.
    Not suitable for public-facing endpoints.

    Defaults: 100 items / page
    Client can override with: ?page_size=200 (max 500)
    """

    page_size              = 100
    page_size_query_param  = "page_size"
    max_page_size          = 500
    page_query_param       = "page"


# ---------------------------------------------------------------------------
# CursorBasedPagination (real-time feeds)
# ---------------------------------------------------------------------------

class CursorBasedPagination(_EnvelopeMixin, CursorPagination):
    """
    Stable, cursor-based pagination for high-write feeds where
    page-number pagination would produce inconsistent results
    (e.g. audit log feed, notification stream).

    Navigate with: ?cursor=<opaque_cursor_string>

    Advantages over PageNumberPagination:
      - Consistent results even if new records are inserted between pages
      - No expensive COUNT(*) query
      - Cannot skip to arbitrary pages (by design — prevents scraping)
    """

    page_size              = 30
    page_size_query_param  = "page_size"
    max_page_size          = 100
    ordering               = "-created_at"

    def _build_envelope(self, data) -> dict:
        """Cursor paginators don't have total count or page numbers."""
        return {
            "success":  True,
            "next":     self.get_next_link(),
            "previous": self.get_previous_link(),
            "results":  data,
        }
