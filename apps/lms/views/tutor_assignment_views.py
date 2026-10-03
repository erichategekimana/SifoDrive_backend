"""
apps/lms/views/tutor_assignment_views.py
========================================
Views for Training Admin assigning Curricula and Courses to Tutors.
"""

from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.constants import UserRole
from apps.accounts.models import User
from apps.core.mixins import SuccessResponseMixin
from apps.core.permissions import IsTrainingAdminOrAbove
from apps.lms.models import (
    Curriculum,
    Course,
    TutorCurriculumAssignment,
    TutorCourseAssignment,
)
from apps.lms.serializers.tutor_assignment_serializers import (
    AssignCoursesSerializer,
    AssignCurriculaSerializer,
    TutorAccreditationSummarySerializer,
    TutorCourseAssignmentSerializer,
    TutorCurriculumAssignmentSerializer,
)
from apps.lms.services import TutorAssignmentService


def _get_tutor_or_404(tutor_id):
    try:
        return User.objects.get(id=tutor_id, role=UserRole.TUTOR)
    except User.DoesNotExist:
        raise NotFound("Tutor account not found.")


class AdminTutorsListView(SuccessResponseMixin, APIView):
    """
    GET /api/v1/lms/admin/tutors/
    Lists all tutors with their accreditation summaries (assigned curricula, courses, and cohorts).
    """

    permission_classes = [IsTrainingAdminOrAbove]

    def get(self, request):
        tutors = User.objects.filter(role=UserRole.TUTOR).order_by("-created_at")
        serializer = TutorAccreditationSummarySerializer(tutors, many=True)
        return self.success_response(data=serializer.data)


class AdminTutorCurriculaAssignmentView(SuccessResponseMixin, APIView):
    """
    GET: View assigned curricula for a tutor.
    POST: Assign/unassign curricula to a tutor (Training Admin+).
    """

    permission_classes = [IsTrainingAdminOrAbove]

    def get(self, request, tutor_id):
        tutor = _get_tutor_or_404(tutor_id)
        assignments = TutorCurriculumAssignment.objects.filter(
            tutor=tutor, is_active=True, is_deleted=False
        ).select_related("curriculum")
        serializer = TutorCurriculumAssignmentSerializer(assignments, many=True)
        return self.success_response(data=serializer.data)

    def post(self, request, tutor_id):
        tutor = _get_tutor_or_404(tutor_id)
        serializer = AssignCurriculaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        curriculum_ids = serializer.validated_data["curriculum_ids"]
        assignments = TutorAssignmentService.assign_curricula_to_tutor(
            tutor=tutor,
            curriculum_ids=curriculum_ids,
            assigned_by=request.user,
        )

        resp_serializer = TutorCurriculumAssignmentSerializer(assignments, many=True)
        return self.success_response(
            data=resp_serializer.data,
            message=f"Successfully updated curricula assignments for {tutor.full_name or tutor.phone_number}.",
        )


class AdminTutorCoursesAssignmentView(SuccessResponseMixin, APIView):
    """
    GET: View assigned courses for a tutor.
    POST: Assign/unassign courses to a tutor (Training Admin+).
    Hard Invariant: All courses must belong to a curriculum already assigned to this tutor.
    """

    permission_classes = [IsTrainingAdminOrAbove]

    def get(self, request, tutor_id):
        tutor = _get_tutor_or_404(tutor_id)
        assignments = TutorCourseAssignment.objects.filter(
            tutor=tutor, is_active=True, is_deleted=False
        ).select_related("course", "course__curriculum")
        serializer = TutorCourseAssignmentSerializer(assignments, many=True)
        return self.success_response(data=serializer.data)

    def post(self, request, tutor_id):
        tutor = _get_tutor_or_404(tutor_id)
        serializer = AssignCoursesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        course_ids = serializer.validated_data["course_ids"]
        assignments = TutorAssignmentService.assign_courses_to_tutor(
            tutor=tutor,
            course_ids=course_ids,
            assigned_by=request.user,
        )

        resp_serializer = TutorCourseAssignmentSerializer(assignments, many=True)
        return self.success_response(
            data=resp_serializer.data,
            message=f"Successfully updated course assignments for {tutor.full_name or tutor.phone_number}.",
        )
