from rest_framework import serializers
from apps.accounts.models import EnterpriseProfile


class EnterpriseProfileSerializer(serializers.ModelSerializer):
    """Serializer for Driving School (Enterprise) Profile."""

    class Meta:
        model = EnterpriseProfile
        fields = [
            "id",
            "school_name",
            "registration_number",
            "district",
            "sector",
            "address_line",
            "contact_email",
            "contact_phone",
            "concurrent_station_quota",
            "is_verified_school",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "registration_number",
            "is_verified_school",
            "created_at",
            "updated_at",
        ]


class EnterpriseStatsSerializer(serializers.Serializer):
    """Response serializer for Enterprise Driving School dashboard stats."""

    school_name = serializers.CharField()
    registration_number = serializers.CharField()
    district = serializers.CharField()
    sector = serializers.CharField(allow_blank=True)
    address_line = serializers.CharField(allow_blank=True)
    contact_email = serializers.CharField(allow_blank=True)
    contact_phone = serializers.CharField(allow_blank=True)
    concurrent_station_quota = serializers.IntegerField()
    active_exam_sessions = serializers.IntegerField()
    available_workstations = serializers.IntegerField()
    utilization_percentage = serializers.FloatField()
    total_students = serializers.IntegerField()
    is_verified = serializers.BooleanField()


class StudentBulkItemSerializer(serializers.Serializer):
    """Single student item in a bulk enrollment batch."""

    phone_number = serializers.CharField(max_length=20)
    first_name = serializers.CharField(max_length=100)
    last_name = serializers.CharField(max_length=100)
    license_category = serializers.CharField(max_length=5, default="B")


class EnterpriseBulkEnrollSerializer(serializers.Serializer):
    """Payload serializer for bulk student registration by driving school."""

    students = serializers.ListField(
        child=StudentBulkItemSerializer(),
        allow_empty=False,
    )
