from rest_framework import serializers

from apps.booking.models import PartnerTeacher
from apps.core.utils import PhoneNumberUtils


class PartnerTeacherDropdownSerializer(serializers.ModelSerializer):
    """Lightweight serializer for applicant dropdown selection."""

    full_name = serializers.CharField(read_only=True)

    class Meta:
        model = PartnerTeacher
        fields = ["id", "full_name", "first_name", "last_name", "phone_number", "driving_school_affiliation"]


class PartnerTeacherAdminSerializer(serializers.ModelSerializer):
    """Full administrative serializer for managing partner driving instructors."""

    full_name = serializers.CharField(read_only=True)

    class Meta:
        model = PartnerTeacher
        fields = [
            "id",
            "first_name",
            "last_name",
            "full_name",
            "phone_number",
            "driving_school_affiliation",
            "is_active",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_phone_number(self, value):
        normalized = PhoneNumberUtils.normalize(value, default_region="RW")
        if not normalized:
            raise serializers.ValidationError("Enter a valid Rwandan phone number.")
        return normalized
