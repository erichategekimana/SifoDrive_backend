from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.accounts.models import StudentProfile

User = get_user_model()


class UserProfileSerializer(serializers.ModelSerializer):
    """
    GET / PATCH /api/v1/auth/me/
    Full profile for the authenticated user. Sensitive fields are excluded.
    """

    full_name = serializers.CharField(read_only=True)
    has_accepted_terms = serializers.BooleanField(read_only=True)
    has_accepted_privacy_policy = serializers.BooleanField(read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "phone_number",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "role",
            "status",
            "student_id",
            "profile_photo",
            "date_of_birth",
            # Consent state (read-only; use /consent/ endpoints to change)
            "has_accepted_terms",
            "has_accepted_privacy_policy",
            "terms_of_service_accepted_at",
            "privacy_policy_accepted_at",
            "created_at",
            "last_login",
        ]
        read_only_fields = [
            "id",
            "phone_number",
            "role",
            "status",
            "student_id",
            "has_accepted_terms",
            "has_accepted_privacy_policy",
            "terms_of_service_accepted_at",
            "privacy_policy_accepted_at",
            "created_at",
            "last_login",
        ]


class StudentProfileSerializer(serializers.ModelSerializer):
    """Student-specific extended profile (language, license category, streak)."""

    class Meta:
        model = StudentProfile
        fields = [
            "preferred_language",
            "license_category",
            "enrollment_date",
            "current_streak_days",
            "longest_streak_days",
            "last_activity_date",
        ]
        read_only_fields = [
            "enrollment_date",
            "current_streak_days",
            "longest_streak_days",
            "last_activity_date",
        ]
