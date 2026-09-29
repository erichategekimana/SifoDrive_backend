from rest_framework import serializers as drf_serializers
from apps.audit.models import AuditLog


class AuditLogSerializer(drf_serializers.ModelSerializer):
    hash_valid = drf_serializers.SerializerMethodField()
    created_at = drf_serializers.DateTimeField(source="timestamp", read_only=True)

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "timestamp",
            "created_at",
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
