"""
apps/lms/serializers.py
========================
LMS serializers — one per model, with access-context awareness.

Naming convention:
  <Model>ListSerializer   — minimal fields for list endpoints (performance)
  <Model>DetailSerializer — full fields for retrieve / create / update
  <Model>WriteSerializer  — fields allowed for write operations (no read-only derived fields)
"""

from rest_framework import serializers

from .models import (
    Course,
    Lesson,
    LessonBookmark,
    LessonQuestion,
    Module,
    QuizQuestion,
    RoadSign,
    StudentProgress,
)


# ===========================================================================
# Road Sign
# ===========================================================================

class RoadSignSerializer(serializers.ModelSerializer):
    class Meta:
        model = RoadSign
        fields = [
            "id", "name", "sign_code", "category",
            "image", "description", "description_kinyarwanda",
            "is_active",
        ]
        read_only_fields = ["id"]


# ===========================================================================
# Quiz Question
# ===========================================================================

class QuizQuestionListSerializer(serializers.ModelSerializer):
    """Compact serializer for question bank lists (no correct answer exposed)."""

    class Meta:
        model = QuizQuestion
        fields = [
            "id", "question_number", "domain", "difficulty",
            "question_text", "question_text_kinyarwanda",
            "option_a", "option_b", "option_c", "option_d",
            "option_a_kinyarwanda", "option_b_kinyarwanda", "option_c_kinyarwanda", "option_d_kinyarwanda",
            "image",
            "option_a_image", "option_b_image", "option_c_image", "option_d_image",
            "road_sign",
        ]
        read_only_fields = ["id"]


class QuizQuestionDetailSerializer(serializers.ModelSerializer):
    """Full serializer including correct answer — for tutors, admins, and post-quiz reveal."""

    correct_text = serializers.CharField(read_only=True)
    road_sign_detail = RoadSignSerializer(source="road_sign", read_only=True)

    class Meta:
        model = QuizQuestion
        fields = [
            "id", "question_number", "domain", "difficulty",
            "question_text", "question_text_kinyarwanda",
            "option_a", "option_b", "option_c", "option_d",
            "option_a_kinyarwanda", "option_b_kinyarwanda", "option_c_kinyarwanda", "option_d_kinyarwanda",
            "correct_option", "correct_text",
            "explanation", "explanation_kinyarwanda",
            "image",
            "option_a_image", "option_b_image", "option_c_image", "option_d_image",
            "road_sign", "road_sign_detail",
            "is_active", "created_by",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "correct_text"]


class QuizQuestionWriteSerializer(serializers.ModelSerializer):
    """Write serializer — used by tutors and admins to create/update questions."""

    class Meta:
        model = QuizQuestion
        fields = [
            "question_number", "domain", "difficulty",
            "question_text", "question_text_kinyarwanda",
            "option_a", "option_b", "option_c", "option_d",
            "option_a_kinyarwanda", "option_b_kinyarwanda", "option_c_kinyarwanda", "option_d_kinyarwanda",
            "correct_option", "explanation", "explanation_kinyarwanda",
            "image",
            "option_a_image", "option_b_image", "option_c_image", "option_d_image",
            "road_sign", "is_active",
        ]

    def validate_correct_option(self, value):
        if value.upper() not in ("A", "B", "C", "D"):
            raise serializers.ValidationError("Correct option must be A, B, C, or D.")
        return value.upper()


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
# Module
# ===========================================================================

class ModuleListSerializer(serializers.ModelSerializer):
    """Compact module info for course detail page."""

    lesson_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Module
        fields = [
            "id", "title", "description", "sort_order",
            "is_foundational", "is_published",
            "lesson_count",
        ]
        read_only_fields = ["id", "lesson_count"]


class ModuleDetailSerializer(serializers.ModelSerializer):
    """Module with full lesson list."""

    lessons   = LessonListSerializer(many=True, read_only=True)
    lesson_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Module
        fields = [
            "id", "course", "title", "description", "sort_order",
            "is_foundational", "is_published", "published_at",
            "lesson_count", "lessons",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "published_at", "lesson_count", "created_at", "updated_at"]


class ModuleWriteSerializer(serializers.ModelSerializer):
    """Write serializer for tutors/admins to create and update modules."""

    class Meta:
        model = Module
        fields = [
            "course", "title", "description",
            "sort_order", "is_foundational",
        ]


# ===========================================================================
# Course
# ===========================================================================

class CourseListSerializer(serializers.ModelSerializer):
    """Compact course card serializer for the catalogue listing."""

    module_count = serializers.IntegerField(read_only=True)
    lesson_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Course
        fields = [
            "id", "title", "description", "thumbnail",
            "estimated_hours", "sort_order",
            "is_published", "published_at",
            "module_count", "lesson_count",
        ]
        read_only_fields = ["id", "published_at", "module_count", "lesson_count"]


class CourseDetailSerializer(serializers.ModelSerializer):
    """Full course with nested modules and lessons."""

    modules      = ModuleDetailSerializer(many=True, read_only=True)
    module_count = serializers.IntegerField(read_only=True)
    lesson_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Course
        fields = [
            "id", "title", "description", "thumbnail",
            "estimated_hours", "sort_order",
            "is_published", "published_at", "published_by",
            "created_by", "updated_by",
            "module_count", "lesson_count",
            "modules",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "published_at", "published_by",
            "created_by", "updated_by",
            "module_count", "lesson_count",
            "created_at", "updated_at",
        ]


class CourseWriteSerializer(serializers.ModelSerializer):
    """Write serializer for tutors/admins to create and update courses."""

    class Meta:
        model = Course
        fields = ["title", "description", "thumbnail", "estimated_hours", "sort_order"]


# ===========================================================================
# Student Progress
# ===========================================================================

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


# ===========================================================================
# Course Stats (admin/tutor)
# ===========================================================================

class CourseStatsSerializer(serializers.Serializer):
    """Response schema for CourseService.get_course_stats()."""

    total_modules     = serializers.IntegerField()
    published_modules = serializers.IntegerField()
    total_lessons     = serializers.IntegerField()
    lesson_breakdown  = serializers.DictField(child=serializers.IntegerField())
    total_questions   = serializers.IntegerField()
    active_students   = serializers.IntegerField()


class ProgressSummarySerializer(serializers.Serializer):
    """Response schema for ProgressService.get_progress_summary()."""

    total_lessons     = serializers.IntegerField()
    completed_lessons = serializers.IntegerField()
    overall_pct       = serializers.FloatField()
    foundational_pct  = serializers.FloatField()
    is_exam_eligible  = serializers.BooleanField()
    time_spent_hours  = serializers.FloatField()
