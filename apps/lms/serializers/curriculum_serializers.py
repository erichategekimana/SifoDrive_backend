"""
apps/lms/serializers/curriculum_serializers.py
===============================================
Serializers for Curricula, Courses, and Modules.
"""

from rest_framework import serializers

from apps.lms.models import Curriculum, Course, Module
from .content_serializers import LessonListSerializer


# ===========================================================================
# Module
# ===========================================================================

class ModuleListSerializer(serializers.ModelSerializer):
    """Compact module info for course detail page."""

    lesson_count = serializers.IntegerField(read_only=True)
    is_locked = serializers.SerializerMethodField()

    class Meta:
        model = Module
        fields = [
            "id", "title", "description", "sort_order",
            "is_foundational", "is_student_only", "is_outside_resource", "is_published", "is_locked",
            "lesson_count",
        ]
        read_only_fields = ["id", "lesson_count", "is_locked"]

    def get_is_locked(self, obj):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        from apps.accounts.constants import UserRole
        if user.role == UserRole.STUDENT:
            from apps.lms.models import CohortModuleRelease
            cohort_ids = list(user.enrolled_cohorts.filter(is_active=True).values_list("id", flat=True))
            if not cohort_ids:
                cohort_ids = list(user.enrolled_cohorts.all().values_list("id", flat=True))
            if not cohort_ids:
                return True
            return not CohortModuleRelease.objects.filter(
                cohort_id__in=cohort_ids,
                module=obj,
                is_published=True,
                is_locked=False,
            ).exists()
        return False


class ModuleDetailSerializer(serializers.ModelSerializer):
    """Module with dynamically filtered lesson list based on requesting user."""

    lessons = serializers.SerializerMethodField()
    lesson_count = serializers.IntegerField(read_only=True)
    is_locked = serializers.SerializerMethodField()

    class Meta:
        model = Module
        fields = [
            "id", "course", "title", "description", "sort_order",
            "is_foundational", "is_student_only", "is_outside_resource", "is_published", "is_locked", "published_at",
            "lesson_count", "lessons",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "published_at", "lesson_count", "is_locked", "created_at", "updated_at"]

    def get_is_locked(self, obj):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        from apps.accounts.constants import UserRole
        if user.role == UserRole.STUDENT:
            from apps.lms.models import CohortModuleRelease
            cohort_ids = list(user.enrolled_cohorts.filter(is_active=True).values_list("id", flat=True))
            if not cohort_ids:
                cohort_ids = list(user.enrolled_cohorts.all().values_list("id", flat=True))
            if not cohort_ids:
                return True
            return not CohortModuleRelease.objects.filter(
                cohort_id__in=cohort_ids,
                module=obj,
                is_published=True,
                is_locked=False,
            ).exists()
        return False

    def get_lessons(self, obj):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        from apps.lms.services import ContentGateService
        visible_lessons = ContentGateService.get_visible_lessons(obj, user)
        return LessonListSerializer(visible_lessons, many=True, context=self.context).data


class ModuleWriteSerializer(serializers.ModelSerializer):
    """Write serializer for tutors/admins to create and update modules."""

    class Meta:
        model = Module
        fields = [
            "course", "title", "description",
            "sort_order", "is_foundational", "is_student_only", "is_outside_resource",
        ]


# ===========================================================================
# Course
# ===========================================================================

class CourseListSerializer(serializers.ModelSerializer):
    """Compact course card serializer for the catalogue listing."""

    module_count = serializers.IntegerField(read_only=True)
    lesson_count = serializers.IntegerField(read_only=True)
    curriculum_title = serializers.CharField(source="curriculum.title", read_only=True, default=None)
    curriculum_code = serializers.CharField(source="curriculum.code", read_only=True, default=None)

    class Meta:
        model = Course
        fields = [
            "id", "curriculum", "curriculum_title", "curriculum_code",
            "code", "title", "title_kinyarwanda",
            "description", "description_kinyarwanda", "thumbnail",
            "estimated_hours", "sort_order",
            "is_published", "published_at",
            "module_count", "lesson_count",
            "homepage_data",
        ]
        read_only_fields = ["id", "published_at", "module_count", "lesson_count"]


class CourseDetailSerializer(serializers.ModelSerializer):
    """Full course with dynamically filtered nested modules and lessons."""

    modules = serializers.SerializerMethodField()
    module_count = serializers.IntegerField(read_only=True)
    lesson_count = serializers.IntegerField(read_only=True)
    curriculum_title = serializers.CharField(source="curriculum.title", read_only=True, default=None)
    curriculum_code = serializers.CharField(source="curriculum.code", read_only=True, default=None)

    class Meta:
        model = Course
        fields = [
            "id", "curriculum", "curriculum_title", "curriculum_code",
            "code", "title", "title_kinyarwanda",
            "description", "description_kinyarwanda", "thumbnail",
            "estimated_hours", "sort_order",
            "is_published", "published_at", "published_by",
            "created_by", "updated_by",
            "module_count", "lesson_count",
            "modules", "homepage_data",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "published_at", "published_by",
            "created_by", "updated_by",
            "module_count", "lesson_count",
            "created_at", "updated_at",
        ]

    def get_modules(self, obj):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        from apps.lms.services import ContentGateService
        visible_modules = ContentGateService.get_visible_modules(obj, user)
        return ModuleDetailSerializer(visible_modules, many=True, context=self.context).data


class CourseWriteSerializer(serializers.ModelSerializer):
    """Write serializer for tutors/admins to create and update courses."""

    class Meta:
        model = Course
        fields = [
            "curriculum", "code", "title", "title_kinyarwanda",
            "description", "description_kinyarwanda",
            "thumbnail", "estimated_hours", "sort_order", "homepage_data",
        ]


class CourseHomepageSerializer(serializers.ModelSerializer):
    """Dedicated serializer for reading and updating course home page builder data."""

    class Meta:
        model = Course
        fields = ["id", "title", "homepage_data", "updated_at"]
        read_only_fields = ["id", "title", "updated_at"]


class CourseStatsSerializer(serializers.Serializer):
    """Response schema for CourseService.get_course_stats()."""

    total_modules     = serializers.IntegerField()
    published_modules = serializers.IntegerField()
    total_lessons     = serializers.IntegerField()
    lesson_breakdown  = serializers.DictField(child=serializers.IntegerField())
    total_questions   = serializers.IntegerField()
    active_students   = serializers.IntegerField()


# ===========================================================================
# Curriculum
# ===========================================================================

class CurriculumListSerializer(serializers.ModelSerializer):
    """List serializer for curricula with course counters."""

    course_count = serializers.IntegerField(read_only=True)
    published_course_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Curriculum
        fields = [
            "id", "title", "title_kinyarwanda", "code", "description",
            "description_kinyarwanda", "thumbnail", "sort_order",
            "is_published", "published_at", "course_count", "published_course_count",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "published_at", "course_count", "published_course_count", "created_at", "updated_at"]


class CurriculumDetailSerializer(serializers.ModelSerializer):
    """Detailed curriculum serializer with nested courses."""

    course_count = serializers.IntegerField(read_only=True)
    published_course_count = serializers.IntegerField(read_only=True)
    courses = CourseListSerializer(many=True, read_only=True)

    class Meta:
        model = Curriculum
        fields = [
            "id", "title", "title_kinyarwanda", "code", "description",
            "description_kinyarwanda", "thumbnail", "sort_order",
            "is_published", "published_at", "published_by", "created_by", "updated_by",
            "course_count", "published_course_count", "courses",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "published_at", "published_by", "created_by", "updated_by",
            "course_count", "published_course_count", "created_at", "updated_at",
        ]


class CurriculumWriteSerializer(serializers.ModelSerializer):
    """Write serializer for System Admin to create and update curricula."""

    class Meta:
        model = Curriculum
        fields = [
            "title", "title_kinyarwanda", "code", "description",
            "description_kinyarwanda", "thumbnail", "sort_order",
        ]
