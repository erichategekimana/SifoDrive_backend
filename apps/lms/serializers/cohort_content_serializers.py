"""
apps/lms/serializers/cohort_content_serializers.py
==================================================
Serializers for cohort-specific module releases and quiz schedules.
"""

from rest_framework import serializers

from apps.lms.models import CohortModuleRelease, CohortQuizSchedule


class CohortModuleReleaseSerializer(serializers.ModelSerializer):
    module_title = serializers.CharField(source="module.title", read_only=True)
    sort_order = serializers.IntegerField(source="module.sort_order", read_only=True)

    class Meta:
        model = CohortModuleRelease
        fields = [
            "id",
            "cohort",
            "module",
            "module_title",
            "sort_order",
            "is_published",
            "is_locked",
            "unlock_date",
            "updated_at",
        ]


class UpdateCohortModuleReleaseSerializer(serializers.Serializer):
    is_published = serializers.BooleanField(required=True)
    is_locked = serializers.BooleanField(required=False, default=False)
    unlock_date = serializers.DateTimeField(required=False, allow_null=True)


class CohortQuizScheduleSerializer(serializers.ModelSerializer):
    quiz_title = serializers.CharField(source="quiz.title", read_only=True)
    quiz_title_kinyarwanda = serializers.CharField(source="quiz.title_kinyarwanda", read_only=True)
    effective_deadline = serializers.DateTimeField(read_only=True)
    status_for_cohort = serializers.CharField(read_only=True)
    allow_tutor_scheduling = serializers.BooleanField(source="quiz.allow_tutor_scheduling", read_only=True)

    class Meta:
        model = CohortQuizSchedule
        fields = [
            "id",
            "cohort",
            "quiz",
            "quiz_title",
            "quiz_title_kinyarwanda",
            "is_published",
            "is_locked",
            "open_date",
            "deadline",
            "extended_deadline",
            "effective_deadline",
            "extension_reason",
            "status_for_cohort",
            "allow_tutor_scheduling",
            "updated_at",
        ]


class ScheduleQuizPayloadSerializer(serializers.Serializer):
    open_date = serializers.DateTimeField(required=False, allow_null=True)
    deadline = serializers.DateTimeField(required=False, allow_null=True)
    is_published = serializers.BooleanField(required=False, default=True)
    is_locked = serializers.BooleanField(required=False, default=False)


class ExtendQuizDeadlinePayloadSerializer(serializers.Serializer):
    extended_deadline = serializers.DateTimeField(required=True)
    reason = serializers.CharField(required=False, allow_blank=True, default="")
