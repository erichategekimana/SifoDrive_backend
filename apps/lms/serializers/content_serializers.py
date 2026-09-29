"""
apps/lms/serializers/content_serializers.py
============================================
Serializers for road signs, lessons, lesson bookmarks, and lesson questions.
"""

from rest_framework import serializers

from apps.lms.models import Lesson, LessonBookmark, LessonQuestion
from .road_sign_serializers import RoadSignSerializer
from .quiz_serializers import QuizQuestionDetailSerializer


# ===========================================================================
# Lesson
# ===========================================================================

class LessonListSerializer(serializers.ModelSerializer):
    """Minimal lesson info for module detail page."""

    question_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Lesson
        fields = [
            "id", "title", "lesson_type", "sort_order",
            "duration_minutes", "is_free_preview", "is_student_only",
            "question_count",
        ]
        read_only_fields = ["id", "question_count"]


class LessonDetailSerializer(serializers.ModelSerializer):
    """Full lesson payload including content (text, media, road sign)."""

    road_sign_detail = RoadSignSerializer(source="road_sign", read_only=True)
    question_count   = serializers.IntegerField(read_only=True)

    class Meta:
        model = Lesson
        fields = [
            "id", "module", "title", "lesson_type", "sort_order",
            "content_text", "media_file", "media_url",
            "road_sign", "road_sign_detail",
            "duration_minutes",
            "is_free_preview", "is_student_only",
            "question_count",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "question_count"]


class LessonWriteSerializer(serializers.ModelSerializer):
    """Write serializer used by tutors and admins to create/edit lessons."""

    class Meta:
        model = Lesson
        fields = [
            "module", "title", "lesson_type", "sort_order",
            "content_text", "media_file", "media_url",
            "road_sign", "duration_minutes",
            "is_free_preview", "is_student_only",
        ]

    def validate(self, data):
        lesson_type = data.get("lesson_type", getattr(self.instance, "lesson_type", None))

        if lesson_type == "TEXT" and not data.get("content_text"):
            raise serializers.ValidationError(
                {"content_text": "Text content is required for TEXT lessons."}
            )
        if lesson_type == "VIDEO" and not (data.get("media_file") or data.get("media_url")):
            raise serializers.ValidationError(
                {"media_url": "A media file or URL is required for VIDEO lessons."}
            )
        if lesson_type == "AUDIO" and not (data.get("media_file") or data.get("media_url")):
            raise serializers.ValidationError(
                {"media_file": "An audio file or audio URL is required for AUDIO lessons."}
            )
        return data


# ===========================================================================
# Lesson Bookmark
# ===========================================================================

class LessonBookmarkSerializer(serializers.ModelSerializer):
    lesson_title = serializers.CharField(source="lesson.title", read_only=True)
    module_title = serializers.CharField(source="lesson.module.title", read_only=True)
    course_title = serializers.CharField(source="lesson.module.course.title", read_only=True)

    class Meta:
        model = LessonBookmark
        fields = [
            "id", "lesson", "lesson_title", "module_title", "course_title",
            "note", "created_at",
        ]
        read_only_fields = ["id", "lesson_title", "module_title", "course_title", "created_at"]

    def create(self, validated_data):
        validated_data["student"] = self.context["request"].user
        return super().create(validated_data)


# ===========================================================================
# Lesson Question (quiz ordering)
# ===========================================================================

class LessonQuestionSerializer(serializers.ModelSerializer):
    question_detail = QuizQuestionDetailSerializer(source="question", read_only=True)

    class Meta:
        model = LessonQuestion
        fields = ["id", "lesson", "question", "sort_order", "question_detail"]
        read_only_fields = ["id"]
