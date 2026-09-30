from rest_framework import serializers
from apps.accounts.models import TutorProfile


class TutorProfileSerializer(serializers.ModelSerializer):
    """Serializer for Tutor Profile details."""

    active_students_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = TutorProfile
        fields = [
            "id",
            "tutor_code",
            "title",
            "bio",
            "specialization_categories",
            "default_meeting_url",
            "is_available_for_tutoring",
            "max_student_capacity",
            "total_teaching_hours",
            "rating",
            "active_students_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "tutor_code",
            "total_teaching_hours",
            "rating",
            "active_students_count",
            "created_at",
            "updated_at",
        ]


class TutorStatsSerializer(serializers.Serializer):
    """Response serializer for Tutor dashboard statistics."""

    tutor_code = serializers.CharField()
    title = serializers.CharField()
    bio = serializers.CharField()
    specialization_categories = serializers.ListField(child=serializers.CharField())
    default_meeting_url = serializers.CharField()
    is_available = serializers.BooleanField()
    max_capacity = serializers.IntegerField()
    total_students = serializers.IntegerField()
    active_students = serializers.IntegerField()
    rating = serializers.FloatField()
    teaching_hours = serializers.IntegerField()


class TutorAssignedStudentSerializer(serializers.Serializer):
    """Response serializer for students assigned to a tutor."""

    id = serializers.CharField()
    full_name = serializers.CharField()
    phone_number = serializers.CharField()
    student_id = serializers.CharField(allow_null=True)
    status = serializers.CharField()
    license_category = serializers.CharField()
    current_streak_days = serializers.IntegerField()
    exam_eligible = serializers.BooleanField()
    attendance_rate = serializers.FloatField()
    module_completion = serializers.FloatField()
