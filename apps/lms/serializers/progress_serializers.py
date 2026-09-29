"""
apps/lms/serializers/progress_serializers.py
=============================================
Serializers for Student Progress, completions, and progress summaries.
"""

from rest_framework import serializers
from apps.lms.models.progress import StudentProgress


class StudentProgressSerializer(serializers.ModelSerializer):
    """Read-only progress record for a student."""

    lesson_title  = serializers.CharField(source="lesson.title", read_only=True)
    lesson_type   = serializers.CharField(source="lesson.lesson_type", read_only=True)
    module_title  = serializers.CharField(source="lesson.module.title", read_only=True)
    course_title  = serializers.CharField(source="lesson.module.course.title", read_only=True)

    class Meta:
        model = StudentProgress
        fields = [
            "id", "lesson", "lesson_title", "lesson_type",
            "module_title", "course_title",
            "is_completed", "completed_at",
            "time_spent_seconds",
            "quiz_score", "quiz_attempts",
        ]
        read_only_fields = fields


class MarkLessonCompleteSerializer(serializers.Serializer):
    """Input for marking a lesson as complete."""

    lesson_id          = serializers.UUIDField()
    time_spent_seconds = serializers.IntegerField(min_value=0, default=0)


class RecordQuizAttemptSerializer(serializers.Serializer):
    """Input for recording a quiz attempt."""

    lesson_id          = serializers.UUIDField()
    score              = serializers.IntegerField(min_value=0, max_value=100)
    time_spent_seconds = serializers.IntegerField(min_value=0, default=0)


class ProgressSummarySerializer(serializers.Serializer):
    """Response schema for ProgressService.get_progress_summary()."""

    total_lessons     = serializers.IntegerField()
    completed_lessons = serializers.IntegerField()
    overall_pct       = serializers.FloatField()
    foundational_pct  = serializers.FloatField()
    is_exam_eligible  = serializers.BooleanField()
    time_spent_hours  = serializers.FloatField()
