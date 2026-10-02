"""
apps/lms/serializers/tutor_assignment_serializers.py
====================================================
Serializers for Training Admin assigning Curricula and Courses to Tutors.
"""

from rest_framework import serializers

from apps.accounts.models import User
from apps.lms.models import (
    Curriculum,
    Course,
    TutorCurriculumAssignment,
    TutorCourseAssignment,
)


class TutorCurriculumAssignmentSerializer(serializers.ModelSerializer):
    curriculum_title = serializers.CharField(source="curriculum.title", read_only=True)
    curriculum_code = serializers.CharField(source="curriculum.code", read_only=True)

    class Meta:
        model = TutorCurriculumAssignment
        fields = [
            "id",
            "curriculum",
            "curriculum_title",
            "curriculum_code",
            "is_active",
            "created_at",
        ]


class TutorCourseAssignmentSerializer(serializers.ModelSerializer):
    course_title = serializers.CharField(source="course.title", read_only=True)
    course_code = serializers.CharField(source="course.code", read_only=True)
    curriculum_id = serializers.UUIDField(source="course.curriculum.id", read_only=True)
    curriculum_title = serializers.CharField(source="course.curriculum.title", read_only=True)

    class Meta:
        model = TutorCourseAssignment
        fields = [
            "id",
            "course",
            "course_title",
            "course_code",
            "curriculum_id",
            "curriculum_title",
            "is_active",
            "created_at",
        ]


class AssignCurriculaSerializer(serializers.Serializer):
    curriculum_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=True,
        help_text="List of curriculum UUIDs assigned to this tutor.",
    )


class AssignCoursesSerializer(serializers.Serializer):
    course_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=True,
        help_text="List of course UUIDs assigned to this tutor.",
    )


class TutorAccreditationSummarySerializer(serializers.ModelSerializer):
    """Summarizes a tutor's active assignments for the Training Admin console."""
    assigned_curricula = serializers.SerializerMethodField()
    assigned_courses = serializers.SerializerMethodField()
    assigned_cohorts = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "first_name",
            "last_name",
            "phone_number",
            "role",
            "is_active",
            "assigned_curricula",
            "assigned_courses",
            "assigned_cohorts",
        ]

    def get_assigned_curricula(self, obj):
        assignments = TutorCurriculumAssignment.objects.filter(
            tutor=obj, is_active=True, is_deleted=False
        ).select_related("curriculum")
        return [
            {
                "id": str(a.curriculum.id),
                "title": a.curriculum.title,
                "code": a.curriculum.code,
            }
            for a in assignments
        ]

    def get_assigned_courses(self, obj):
        assignments = TutorCourseAssignment.objects.filter(
            tutor=obj, is_active=True, is_deleted=False
        ).select_related("course", "course__curriculum")
        return [
            {
                "id": str(a.course.id),
                "title": a.course.title,
                "code": a.course.code,
                "curriculum_id": str(a.course.curriculum_id) if a.course.curriculum_id else None,
                "curriculum_title": a.course.curriculum.title if a.course.curriculum else "",
            }
            for a in assignments
        ]

    def get_assigned_cohorts(self, obj):
        cohorts = obj.assigned_cohorts.filter(is_active=True)
        return [
            {
                "id": str(c.id),
                "name": c.name,
                "code": c.code,
                "student_count": c.students.count(),
            }
            for c in cohorts
        ]
