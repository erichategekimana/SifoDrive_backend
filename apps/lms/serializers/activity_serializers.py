"""
apps/lms/serializers/activity_serializers.py
============================================
Serializers for tutor cohort activities and student submissions.
"""

from rest_framework import serializers

from apps.lms.models import CohortActivity, StudentActivitySubmission


class CohortActivitySerializer(serializers.ModelSerializer):
    cohort_name = serializers.CharField(source="cohort.name", read_only=True)
    course_title = serializers.CharField(source="course.title", read_only=True)
    module_title = serializers.CharField(source="module.title", read_only=True, allow_null=True)
    created_by_name = serializers.CharField(source="created_by.full_name", read_only=True)
    submission_count = serializers.IntegerField(read_only=True)
    graded_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = CohortActivity
        fields = [
            "id",
            "cohort",
            "cohort_name",
            "course",
            "course_title",
            "module",
            "module_title",
            "created_by",
            "created_by_name",
            "title",
            "title_kinyarwanda",
            "description",
            "description_kinyarwanda",
            "activity_type",
            "submission_type",
            "total_points",
            "passing_points",
            "due_date",
            "allow_late_submission",
            "is_published",
            "is_locked",
            "submission_count",
            "graded_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_by", "created_at", "updated_at"]


class StudentActivitySubmissionSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    student_phone = serializers.CharField(source="student.phone_number", read_only=True)
    activity_title = serializers.CharField(source="activity.title", read_only=True)
    graded_by_name = serializers.CharField(source="graded_by.full_name", read_only=True)

    class Meta:
        model = StudentActivitySubmission
        fields = [
            "id",
            "activity",
            "activity_title",
            "student",
            "student_name",
            "student_phone",
            "submission_text",
            "attachment",
            "submitted_at",
            "status",
            "score",
            "tutor_feedback",
            "graded_by",
            "graded_by_name",
            "graded_at",
        ]
        read_only_fields = [
            "activity",
            "student",
            "submitted_at",
            "status",
            "score",
            "tutor_feedback",
            "graded_by",
            "graded_at",
        ]


class GradeSubmissionPayloadSerializer(serializers.Serializer):
    score = serializers.DecimalField(max_digits=5, decimal_places=2, required=True)
    feedback = serializers.CharField(required=False, allow_blank=True, default="")
