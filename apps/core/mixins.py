"""
apps/core/mixins.py
=====================
Reusable DRF view mixins providing:
  - Consistent JSON response envelopes           (SuccessResponseMixin)
  - Soft delete integration                       (SoftDeleteMixin)
  - Automatic created_by / updated_by tracking   (AuditableViewMixin)
  - Enforce GET-only access                       (ReadOnlyMixin)
  - Enforce ownership before object access        (OwnershipMixin)
  - Consistent list response with metadata        (ListResponseMixin)

Composition pattern (all mixins are designed to stack):
    class MyView(SoftDeleteMixin, AuditableViewMixin, SuccessResponseMixin, generics.RetrieveUpdateDestroyAPIView):
        ...
"""

from rest_framework import status
from rest_framework.response import Response


# ===========================================================================
# Response Envelope Mixin
# ===========================================================================

class SuccessResponseMixin:
    """
    Standardises all successful API responses into the envelope:

        {
            "success": true,
            "message": "Optional human-readable message.",
            "data": { ... }
        }

    Available methods:
        self.success_response(data, message, status_code)   → 200 by default
        self.created_response(data, message)                → 201
        self.accepted_response(data, message)               → 202 (async tasks)
        self.no_content_response()                          → 204
        self.error_response(code, message, status_code)     → custom error
    """

    def success_response(
        self,
        data=None,
        message: str | None = None,
        status_code: int = status.HTTP_200_OK,
        meta: dict | None = None,
    ) -> Response:
        """
        Build a successful response.

        Args:
            data:        The payload (dict, list, or None).
            message:     Optional human-readable description.
            status_code: HTTP status code (default 200).
            meta:        Optional extra metadata (e.g. processing time, flags).
        """
        payload: dict = {"success": True}
        if message:
            payload["message"] = message
        if data is not None:
            payload["data"] = data
        if meta:
            payload["meta"] = meta
        return Response(payload, status=status_code)

    def created_response(
        self,
        data=None,
        message: str = "Created successfully.",
        meta: dict | None = None,
    ) -> Response:
        """Convenience wrapper for HTTP 201 Created."""
        return self.success_response(
            data=data,
            message=message,
            status_code=status.HTTP_201_CREATED,
            meta=meta,
        )

    def accepted_response(
        self,
        data=None,
        message: str = "Request accepted. Processing asynchronously.",
    ) -> Response:
        """
        HTTP 202 Accepted — for async operations like Celery task dispatch.
        The task ID or tracking reference should be in `data`.
        """
        return self.success_response(
            data=data,
            message=message,
            status_code=status.HTTP_202_ACCEPTED,
        )

    def no_content_response(self) -> Response:
        """HTTP 204 No Content — for successful deletes or resets."""
        return Response(status=status.HTTP_204_NO_CONTENT)

    def error_response(
        self,
        code: str,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: dict | None = None,
    ) -> Response:
        """
        Build a structured error response without raising an exception.
        Use this for expected inline error cases inside views.

        For unexpected or domain errors, raise an exception instead
        and let the custom_exception_handler convert it.
        """
        error_block = {"code": code, "message": message}
        if details:
            error_block["details"] = details
        return Response(
            {"success": False, "error": error_block},
            status=status_code,
        )


# ===========================================================================
# Soft Delete Mixin
# ===========================================================================

class SoftDeleteMixin:
    """
    Overrides DRF's DestroyModelMixin.perform_destroy() to call
    instance.delete(deleted_by=user) instead of instance.hard_delete().

    Works with any model that inherits SoftDeleteModel.
    The actor (request.user) is recorded as deleted_by on the record.
    """

    def perform_destroy(self, instance) -> None:
        instance.delete(deleted_by=self.request.user)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return SuccessResponseMixin.no_content_response(self)


# ===========================================================================
# Auditable View Mixin
# ===========================================================================

class AuditableViewMixin:
    """
    Automatically injects created_by / updated_by into serializer saves
    when those fields exist on the target model.

    Also hooks into the audit service to record CREATE/UPDATE events
    if the model has a corresponding AuditService method.
    """

    def perform_create(self, serializer):
        kwargs = {}
        model = serializer.Meta.model
        if hasattr(model, "created_by_id"):
            kwargs["created_by"] = self.request.user
        instance = serializer.save(**kwargs)
        self._audit_create(instance)
        return instance

    def perform_update(self, serializer):
        kwargs = {}
        model = serializer.Meta.model
        if hasattr(model, "updated_by_id"):
            kwargs["updated_by"] = self.request.user
        instance = serializer.save(**kwargs)
        self._audit_update(instance)
        return instance

    def _audit_create(self, instance) -> None:
        """Override in subclasses to fire a specific AuditService.log_* method."""

    def _audit_update(self, instance) -> None:
        """Override in subclasses to fire a specific AuditService.log_* method."""


# ===========================================================================
# Read-Only Mixin
# ===========================================================================

class ReadOnlyMixin:
    """
    Restricts the view to read-only HTTP methods at the class level.
    Any POST/PUT/PATCH/DELETE will receive HTTP 405 Method Not Allowed.
    """

    http_method_names = ["get", "head", "options"]


# ===========================================================================
# Ownership Mixin
# ===========================================================================

class OwnershipMixin:
    """
    Enforces that the requesting user owns the object being accessed.
    Checks for `owner`, `user`, or `student` FK fields on the model.
    SYSTEM_ADMIN bypasses the ownership check.

    Combine with get_object() in your view:

        class MyView(OwnershipMixin, generics.RetrieveAPIView):
            def get_object(self):
                obj = super().get_object()
                self.check_ownership(obj)
                return obj
    """

    def check_ownership(self, obj) -> None:
        """
        Raise PermissionDenied if the requesting user does not own the object.
        """
        from apps.accounts.constants import UserRole
        from rest_framework.exceptions import PermissionDenied

        user = self.request.user
        if user.role == UserRole.SYSTEM_ADMIN:
            return  # Admins bypass ownership

        owner = (
            getattr(obj, "owner", None)
            or getattr(obj, "user", None)
            or getattr(obj, "student", None)
            or getattr(obj, "applicant", None)
            or getattr(obj, "payer", None)
        )
        if owner is None or owner != user:
            raise PermissionDenied(
                "You do not have permission to access this resource."
            )


# ===========================================================================
# List Response Mixin
# ===========================================================================

class ListResponseMixin(SuccessResponseMixin):
    """
    Wraps paginated list responses in the standard envelope with metadata.
    Works alongside StandardResultsPagination.

    Typically you won't need to use this directly — the paginator's
    get_paginated_response() already wraps in the envelope.
    Use this when you need to manually build a list response.
    """

    def list_response(
        self,
        data: list,
        total: int | None = None,
        message: str | None = None,
    ) -> Response:
        payload: dict = {
            "success": True,
            "count":   total if total is not None else len(data),
            "results": data,
        }
        if message:
            payload["message"] = message
        return Response(payload, status=status.HTTP_200_OK)
