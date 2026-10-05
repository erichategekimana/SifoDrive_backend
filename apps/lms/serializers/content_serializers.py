"""
apps/lms/serializers/content_serializers.py
============================================
Serializers for road signs, lessons, lesson bookmarks, and lesson questions.
"""

from rest_framework import serializers

from apps.lms.models import Lesson, LessonBookmark, LessonContent, LessonQuestion
from .road_sign_serializers import RoadSignSerializer
from .quiz_serializers import QuizQuestionDetailSerializer


# ===========================================================================
# Lesson Content
# ===========================================================================

class LessonContentSerializer(serializers.ModelSerializer):
    """Full serializer for individual lesson content blocks."""

    class Meta:
        model = LessonContent
        fields = [
            "id", "lesson", "title", "content_type", "document_type",
            "sort_order", "duration_minutes", "content_text",
            "media_file", "media_url", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class LessonContentWriteSerializer(serializers.ModelSerializer):
    """Write serializer for creating and updating lesson content items."""

    class Meta:
        model = LessonContent
        fields = [
            "lesson", "title", "content_type", "document_type",
            "sort_order", "duration_minutes", "content_text",
            "media_file", "media_url",
        ]


# ===========================================================================
# Lesson
# ===========================================================================

class LessonListSerializer(serializers.ModelSerializer):
    """Minimal lesson info for module detail page with contents info."""

    question_count = serializers.IntegerField(read_only=True)
    content_count  = serializers.IntegerField(read_only=True)
    content_types  = serializers.SerializerMethodField()

    class Meta:
        model = Lesson
        fields = [
            "id", "title", "lesson_type", "sort_order",
            "duration_minutes", "is_free_preview", "is_student_only", "is_outside_resource",
            "question_count", "content_count", "content_types",
        ]
        read_only_fields = ["id", "question_count", "content_count", "content_types"]

    def get_content_types(self, obj):
        return list(obj.contents.values_list("content_type", flat=True).distinct())


class LessonDetailSerializer(serializers.ModelSerializer):
    """Full lesson payload including all attached modular contents."""

    road_sign_detail = RoadSignSerializer(source="road_sign", read_only=True)
    question_count   = serializers.IntegerField(read_only=True)
    contents         = LessonContentSerializer(many=True, read_only=True)
    content_count    = serializers.IntegerField(read_only=True)

    class Meta:
        model = Lesson
        fields = [
            "id", "module", "title", "lesson_type", "sort_order",
            "content_text", "media_file", "media_url",
            "road_sign", "road_sign_detail",
            "duration_minutes",
            "is_free_preview", "is_student_only", "is_outside_resource",
            "question_count", "contents", "content_count",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "question_count", "content_count"]


class LessonWriteSerializer(serializers.ModelSerializer):
    """Write serializer used by tutors and admins to create/edit lessons."""

    contents_payload = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        write_only=True,
        help_text="Optional list of content dicts to create with lesson.",
    )

    class Meta:
        model = Lesson
        fields = [
            "module", "title", "lesson_type", "sort_order",
            "content_text", "media_file", "media_url",
            "road_sign", "duration_minutes",
            "is_free_preview", "is_student_only", "is_outside_resource",
            "contents_payload",
        ]

    def validate(self, data):
        lesson_type = data.get("lesson_type", getattr(self.instance, "lesson_type", None))
        contents_payload = data.get("contents_payload", [])

        # If MULTI or if contents_payload is provided, single-field validation is relaxed
        if lesson_type in ("MULTI",) or contents_payload:
            return data

        if lesson_type == "TEXT" and not data.get("content_text") and not getattr(self.instance, "content_text", None):
            # Check if lesson has attached contents
            if not (self.instance and self.instance.contents.exists()):
                raise serializers.ValidationError(
                    {"content_text": "Text content or attached contents are required for TEXT lessons."}
                )
        if lesson_type == "VIDEO" and not (data.get("media_file") or data.get("media_url")):
            if not (self.instance and self.instance.contents.filter(content_type="VIDEO").exists()):
                raise serializers.ValidationError(
                    {"media_url": "A media file or URL is required for VIDEO lessons."}
                )
        if lesson_type == "AUDIO" and not (data.get("media_file") or data.get("media_url")):
            if not (self.instance and self.instance.contents.filter(content_type="AUDIO").exists()):
                raise serializers.ValidationError(
                    {"media_file": "An audio file or audio URL is required for AUDIO lessons."}
                )
        return data

    def create(self, validated_data):
        contents_payload = validated_data.pop("contents_payload", [])
        lesson = super().create(validated_data)
        for idx, item in enumerate(contents_payload):
            LessonContent.objects.create(
                lesson=lesson,
                title=item.get("title", ""),
                content_type=item.get("content_type", "TEXT"),
                document_type=item.get("document_type", "OTHER"),
                sort_order=item.get("sort_order", idx + 1),
                duration_minutes=item.get("duration_minutes", 0),
                content_text=item.get("content_text", ""),
                media_url=item.get("media_url", ""),
            )
        return lesson

    def update(self, instance, validated_data):
        contents_payload = validated_data.pop("contents_payload", None)
        lesson = super().update(instance, validated_data)
        if contents_payload is not None and len(contents_payload) > 0:
            # Upsert or replace contents
            for idx, item in enumerate(contents_payload):
                cid = item.get("id")
                if cid:
                    LessonContent.objects.filter(id=cid, lesson=lesson).update(
                        title=item.get("title", ""),
                        content_type=item.get("content_type", "TEXT"),
                        document_type=item.get("document_type", "OTHER"),
                        sort_order=item.get("sort_order", idx + 1),
                        duration_minutes=item.get("duration_minutes", 0),
                        content_text=item.get("content_text", ""),
                        media_url=item.get("media_url", ""),
                    )
                else:
                    LessonContent.objects.create(
                        lesson=lesson,
                        title=item.get("title", ""),
                        content_type=item.get("content_type", "TEXT"),
                        document_type=item.get("document_type", "OTHER"),
                        sort_order=item.get("sort_order", idx + 1),
                        duration_minutes=item.get("duration_minutes", 0),
                        content_text=item.get("content_text", ""),
                        media_url=item.get("media_url", ""),
                    )
        return lesson


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
