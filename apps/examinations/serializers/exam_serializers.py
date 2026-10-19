"""
apps/examinations/serializers/exam_serializers.py
=================================================
Serializers for official Exam management.
"""

from rest_framework import serializers
from apps.examinations.models import Exam


class AdminExamSerializer(serializers.Serializer):
    """
    Serializer for Training Admin and System Admin exam scheduling.
    Questions cannot be manually chosen or assigned.
    """
    id = serializers.CharField(read_only=True)
    title = serializers.CharField(max_length=255, required=True)
    title_kinyarwanda = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    title_french = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    exam_type = serializers.ChoiceField(choices=["STUDENT", "PUBLIC_PRACTICE"], default="STUDENT")
    status = serializers.ChoiceField(choices=["DRAFT", "PUBLISHED", "CLOSED"], default="DRAFT")

    cohort_id = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    cohort_name = serializers.CharField(required=False, allow_blank=True, default="")

    open_date = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    due_date = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    closing_date = serializers.CharField(required=False, allow_null=True, allow_blank=True)

    instructions = serializers.CharField(required=False, allow_blank=True, default="")
    instructions_kinyarwanda = serializers.CharField(required=False, allow_blank=True, default="")
    instructions_french = serializers.CharField(required=False, allow_blank=True, default="")

    rubric = serializers.CharField(required=False, allow_blank=True, default="")
    rubric_kinyarwanda = serializers.CharField(required=False, allow_blank=True, default="")
    rubric_french = serializers.CharField(required=False, allow_blank=True, default="")

    is_published = serializers.BooleanField(default=False)

    # Immutable engine parameters (read-only)
    total_questions = serializers.IntegerField(default=20, read_only=True)
    duration_minutes = serializers.IntegerField(default=20, read_only=True)
    points_per_question = serializers.IntegerField(default=1, read_only=True)
    passing_score = serializers.IntegerField(default=12, read_only=True)

    created_at = serializers.CharField(read_only=True)
    updated_at = serializers.CharField(read_only=True)
    created_by_name = serializers.CharField(read_only=True)
    active_sessions_count = serializers.IntegerField(default=0, read_only=True)
    completed_sessions_count = serializers.IntegerField(default=0, read_only=True)

    def validate(self, attrs):
        title = attrs.get("title", "").strip()
        if not title:
            raise serializers.ValidationError({"title": "Exam title is required."})

        # Explicitly disallow any attempt to attach questions
        if "questions" in self.initial_data or "question_ids" in self.initial_data:
            raise serializers.ValidationError(
                {"questions": "Exam questions are generated automatically by the random 20-question domain engine and cannot be manually selected."}
            )

        return attrs
