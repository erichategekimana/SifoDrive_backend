"""
apps/lms/serializers/activity_serializers.py
============================================
Serializers for tutor cohort activities and student submissions.
"""

from rest_framework import serializers
from apps.live_classes.models import Cohort
from apps.lms.models import CohortActivity, StudentActivitySubmission


class CohortActivitySerializer(serializers.ModelSerializer):
    cohort = serializers.PrimaryKeyRelatedField(queryset=Cohort.objects.all(), required=False)
    cohort_name = serializers.CharField(source="cohort.name", read_only=True)
    course_title = serializers.CharField(source="course.title", read_only=True)
    module_title = serializers.CharField(source="module.title", read_only=True, allow_null=True)
    created_by_name = serializers.CharField(source="created_by.full_name", read_only=True)
    submission_count = serializers.IntegerField(read_only=True)
    graded_count = serializers.IntegerField(read_only=True)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    activity_type = serializers.CharField(required=False, default="ASSIGNMENT")
    submission_type = serializers.CharField(required=False, default="TEXT_RESPONSE")
    total_points = serializers.IntegerField(required=False, default=100)
    passing_points = serializers.IntegerField(required=False, default=70)
    grades_published = serializers.BooleanField(required=False, default=False)
    release_grades_immediately = serializers.BooleanField(required=False, default=False)
    attachment_file = serializers.SerializerMethodField()

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
            "allowed_submission_methods",
            "resource_type",
            "attachment",
            "attachment_file",
            "attachment_url",
            "total_points",
            "passing_points",
            "open_date",
            "due_date",
            "allow_late_submission",
            "is_published",
            "is_locked",
            "grades_published",
            "release_grades_immediately",
            "submission_count",
            "graded_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_by", "created_at", "updated_at"]

    def get_attachment_file(self, obj):
        if not obj.attachment:
            return None
        request = self.context.get("request")
        if request:
            return request.build_absolute_uri(obj.attachment.url)
        return obj.attachment.url

    def validate(self, attrs):
        # Fallback description if blank
        if not attrs.get("description"):
            attrs["description"] = (
                self.initial_data.get("instructions")
                or self.initial_data.get("description")
                or attrs.get("title")
                or "Activity"
            )

        # Normalize total_points & passing_points from max_score / pass_score aliases
        if "max_score" in self.initial_data and "total_points" not in attrs:
            try:
                attrs["total_points"] = int(self.initial_data["max_score"])
            except (ValueError, TypeError):
                pass
        if "pass_score" in self.initial_data and "passing_points" not in attrs:
            try:
                attrs["passing_points"] = int(self.initial_data["pass_score"])
            except (ValueError, TypeError):
                pass

        # Validate activity_type choices
        valid_act_types = {"ASSIGNMENT", "PRACTICAL_DRILL", "CASE_STUDY", "DISCUSSION", "READING_EXERCISE"}
        if attrs.get("activity_type") not in valid_act_types:
            attrs["activity_type"] = "ASSIGNMENT"

        # Validate submission_type choices
        valid_sub_types = {"FILE_UPLOAD", "TEXT_RESPONSE", "PRACTICAL_EVALUATION", "NONE"}
        if attrs.get("submission_type") not in valid_sub_types:
            attrs["submission_type"] = "TEXT_RESPONSE"

        # Ensure allowed_submission_methods is a list if received as a serialized string
        methods = attrs.get("allowed_submission_methods")
        if isinstance(methods, str):
            import json
            try:
                attrs["allowed_submission_methods"] = json.loads(methods)
            except Exception:
                attrs["allowed_submission_methods"] = [m.strip() for m in methods.split(",") if m.strip()]

        # Validate grades_published: cannot publish before open_date or due_date has arrived/passed
        if attrs.get("grades_published") is True:
            from django.utils import timezone
            now = timezone.now()
            open_date = attrs.get("open_date") or getattr(self.instance, "open_date", None)
            due_date = attrs.get("due_date") or getattr(self.instance, "due_date", None)
            if open_date and open_date > now:
                formatted = open_date.strftime("%Y-%m-%d %H:%M")
                raise serializers.ValidationError({
                    "grades_published": f"Cannot publish grades before the activity open date ({formatted})."
                })
            if due_date and due_date > now:
                formatted = due_date.strftime("%Y-%m-%d %H:%M")
                raise serializers.ValidationError({
                    "grades_published": f"Cannot publish grades before the activity deadline ({formatted})."
                })

        return attrs


class StudentActivitySubmissionSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    student_phone = serializers.CharField(source="student.phone_number", read_only=True)
    activity_title = serializers.CharField(source="activity.title", read_only=True)
    graded_by_name = serializers.CharField(source="graded_by.full_name", read_only=True)
    text_content = serializers.CharField(source="submission_text", read_only=True)
    attachment_file = serializers.SerializerMethodField()
    attachment_url = serializers.SerializerMethodField()

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
            "text_content",
            "submission_link",
            "submission_method",
            "attachment",
            "attachment_file",
            "attachment_url",
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

    def get_attachment_file(self, obj):
        if not obj.attachment:
            return None
        request = self.context.get("request")
        if request:
            return request.build_absolute_uri(obj.attachment.url)
        return obj.attachment.url

    def get_attachment_url(self, obj):
        return self.get_attachment_file(obj)


class GradeSubmissionPayloadSerializer(serializers.Serializer):
    score = serializers.DecimalField(max_digits=5, decimal_places=2, required=True)
    feedback = serializers.CharField(required=False, allow_blank=True, default="")
