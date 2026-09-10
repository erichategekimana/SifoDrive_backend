"""
apps/audit/views.py
====================
Read-only REST API for audit logs.
Access: SYSTEM_ADMIN and BOARD_REVIEWER only.
All views are GET-only — no write endpoints exist for audit logs.
"""

from rest_framework import generics, serializers as drf_serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.mixins import SuccessResponseMixin
from apps.core.permissions import IsAdminLevel

from .models import AuditLog, AuditSeverity


# ---------------------------------------------------------------------------
# Serializer
# ---------------------------------------------------------------------------

class AuditLogSerializer(drf_serializers.ModelSerializer):
    hash_valid = drf_serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "timestamp",
            "action",
            "severity",
            "performed_by_id",
            "performed_by_phone",
            "target_user_id",
            "object_type",
            "object_id",
            "ip_address",
            "request_id",
            "http_method",
            "endpoint",
            "context",
            "record_hash",
            "hash_valid",
        ]
        read_only_fields = fields

    def get_hash_valid(self, obj) -> bool | None:
        """Include hash verification in API responses for ops tooling."""
        if not obj.record_hash:
            return None
        return obj.verify_hash()


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

class AuditLogListView(SuccessResponseMixin, generics.ListAPIView):
    """
    GET /api/v1/audit/logs/

    Paginated, filterable audit log stream.
    Accessible by SYSTEM_ADMIN and BOARD_REVIEWER.

    Query params:
      ?action=NID_ACCESS
      ?severity=CRITICAL
      ?performed_by_id=<uuid>
      ?target_user_id=<uuid>
      ?object_type=BookingOrder
    """

    permission_classes = [IsAdminLevel]
    serializer_class = AuditLogSerializer
    filterset_fields = ["action", "severity", "http_method", "object_type"]
    search_fields = [
        "performed_by_id",
        "target_user_id",
        "object_id",
        "request_id",
        "ip_address",
    ]
    ordering_fields = ["timestamp", "severity", "action"]
    ordering = ["-timestamp"]

    def get_queryset(self):
        qs = AuditLog.objects.all()
        # Optional filters via query params
        params = self.request.query_params
        if uid := params.get("performed_by_id"):
            qs = qs.by_user(uid)
        if uid := params.get("target_user_id"):
            qs = qs.filter(target_user_id=uid)
        if obj_id := params.get("object_id"):
            qs = qs.filter(object_id=obj_id)
        return qs


class AuditLogDetailView(SuccessResponseMixin, generics.RetrieveAPIView):
    """
    GET /api/v1/audit/logs/<uuid>/
    Retrieve a single audit log entry with hash verification status.
    """

    permission_classes = [IsAdminLevel]
    serializer_class = AuditLogSerializer
    queryset = AuditLog.objects.all()
    lookup_field = "id"


class UserAuditTrailView(SuccessResponseMixin, generics.ListAPIView):
    """
    GET /api/v1/audit/users/<user_id>/

    Complete audit trail for a specific user — all events performed BY them
    or targeting their account. Used by SYSTEM_ADMIN for compliance investigations.
    """

    permission_classes = [IsAdminLevel]
    serializer_class = AuditLogSerializer
    ordering = ["-timestamp"]

    def get_queryset(self):
        user_id = self.kwargs["user_id"]
        return AuditLog.objects.concerning_user(user_id)


class CriticalEventsView(SuccessResponseMixin, generics.ListAPIView):
    """
    GET /api/v1/audit/critical/

    Fast-access view for ops monitoring — returns only HIGH and CRITICAL events
    from the last 24 hours by default.
    """

    permission_classes = [IsAdminLevel]
    serializer_class = AuditLogSerializer
    ordering = ["-timestamp"]

    def get_queryset(self):
        from django.utils import timezone
        from datetime import timedelta
        since = timezone.now() - timedelta(hours=24)
        return AuditLog.objects.high_and_above().filter(timestamp__gte=since)


class IntegrityStatsView(SuccessResponseMixin, APIView):
    """
    GET /api/v1/audit/integrity/
    Quick integrity summary: how many records pass/fail hash verification
    from the most recent 1000 entries.
    For full check, use: python manage.py verify_audit_integrity
    """

    permission_classes = [IsAdminLevel]

    def get(self, request, *args, **kwargs):
        recent = AuditLog.objects.order_by("-timestamp")[:1000]
        total = len(recent)
        failed = [log for log in recent if log.record_hash and not log.verify_hash()]
        return self.success_response(
            data={
                "checked": total,
                "passed": total - len(failed),
                "failed": len(failed),
                "all_passed": len(failed) == 0,
                "tampered_ids": [str(log.id) for log in failed],
            }
        )
