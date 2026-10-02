"""
apps/lms/views/activity_views.py
================================
Views for Tutor cohort activities creation, student submissions, and grading.
"""

from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.views import APIView

from apps.accounts.constants import UserRole
from apps.core.mixins import SuccessResponseMixin
from apps.core.permissions import IsStaffOrAdmin, IsStudentOrStaff
from apps.live_classes.models import Cohort
from apps.lms.models import (
    CohortActivity,
    Course,
    Module,
    StudentActivitySubmission,
)
from apps.lms.serializers.activity_serializers import (
    CohortActivitySerializer,
    GradeSubmissionPayloadSerializer,
    StudentActivitySubmissionSerializer,
)
from apps.lms.services import CohortActivityService


def _get_cohort_and_validate_tutor(cohort_id, user):
    try:
        cohort = Cohort.objects.get(id=cohort_id)
    except Cohort.DoesNotExist:
        raise NotFound("Cohort not found.")

    if user.role in (UserRole.SYSTEM_ADMIN, UserRole.TRAINING_ADMIN) or user.is_superuser:
        return cohort

    if user.role == UserRole.TUTOR:
        if not cohort.assigned_tutors.filter(id=user.id).exists():
            raise PermissionDenied("You are not assigned to instruct this cohort.")
        return cohort

    raise PermissionDenied("Access denied.")


class TutorCohortActivitiesListCreateView(SuccessResponseMixin, APIView):
    """
    GET: List activities for a cohort.
    POST: Create a new activity for a cohort (Tutor & Admin).
    """

    permission_classes = [IsStaffOrAdmin]

    def get(self, request, cohort_id):
        cohort = _get_cohort_and_validate_tutor(cohort_id, request.user)
        course_id = request.query_params.get("course_id")
        qs = CohortActivity.objects.filter(cohort=cohort, is_deleted=False)
        if course_id:
            qs = qs.filter(course_id=course_id)
        serializer = CohortActivitySerializer(qs, many=True)
        return self.success_response(data=serializer.data)

    def post(self, request, cohort_id):
        cohort = _get_cohort_and_validate_tutor(cohort_id, request.user)
        serializer = CohortActivitySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        course = data["course"]
        module = data.get("module")

        activity = CohortActivityService.create_activity(
            cohort=cohort,
            course=course,
            module=module,
            title=data["title"],
            description=data["description"],
            title_kinyarwanda=data.get("title_kinyarwanda", ""),
            description_kinyarwanda=data.get("description_kinyarwanda", ""),
            activity_type=data.get("activity_type", "ASSIGNMENT"),
            submission_type=data.get("submission_type", "TEXT_RESPONSE"),
            total_points=data.get("total_points", 100),
            passing_points=data.get("passing_points", 70),
            due_date=data.get("due_date"),
            allow_late_submission=data.get("allow_late_submission", False),
            is_published=data.get("is_published", True),
            is_locked=data.get("is_locked", False),
            tutor=request.user,
        )

        resp_serializer = CohortActivitySerializer(activity)
        return self.created_response(
            data=resp_serializer.data,
            message=f"Activity '{activity.title}' created successfully for cohort '{cohort.name}'.",
        )


class TutorCohortActivityDetailUpdateDeleteView(SuccessResponseMixin, APIView):
    """
    GET, PATCH, DELETE a specific cohort activity.
    """

    permission_classes = [IsStaffOrAdmin]

    def get_object(self, cohort_id, activity_id, user):
        cohort = _get_cohort_and_validate_tutor(cohort_id, user)
        try:
            return CohortActivity.objects.get(id=activity_id, cohort=cohort, is_deleted=False)
        except CohortActivity.DoesNotExist:
            raise NotFound("Activity not found.")

    def get(self, request, cohort_id, activity_id):
        activity = self.get_object(cohort_id, activity_id, request.user)
        return self.success_response(data=CohortActivitySerializer(activity).data)

    def patch(self, request, cohort_id, activity_id):
        activity = self.get_object(cohort_id, activity_id, request.user)
        serializer = CohortActivitySerializer(activity, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = serializer.save()
        return self.success_response(
            data=CohortActivitySerializer(updated).data,
            message="Activity updated successfully.",
        )

    def delete(self, request, cohort_id, activity_id):
        activity = self.get_object(cohort_id, activity_id, request.user)
        activity.is_deleted = True
        activity.save(update_fields=["is_deleted", "updated_at"])
        return self.success_response(message="Activity deleted successfully.")


class TutorCohortActivitySubmissionsListView(SuccessResponseMixin, APIView):
    """
    GET /api/v1/lms/tutor/cohorts/<uuid:cohort_id>/activities/<uuid:activity_id>/submissions/
    Returns all student submissions for an activity.
    """

    permission_classes = [IsStaffOrAdmin]

    def get(self, request, cohort_id, activity_id):
        cohort = _get_cohort_and_validate_tutor(cohort_id, request.user)
        try:
            activity = CohortActivity.objects.get(id=activity_id, cohort=cohort, is_deleted=False)
        except CohortActivity.DoesNotExist:
            raise NotFound("Activity not found.")

        submissions = activity.submissions.filter(is_deleted=False).select_related("student")
        serializer = StudentActivitySubmissionSerializer(submissions, many=True)
        return self.success_response(data=serializer.data)


class TutorCohortActivityGradeSubmissionView(SuccessResponseMixin, APIView):
    """
    POST /api/v1/lms/tutor/cohorts/<uuid:cohort_id>/activities/<uuid:activity_id>/submissions/<uuid:submission_id>/grade/
    Grades a submission and gives tutor feedback.
    """

    permission_classes = [IsStaffOrAdmin]

    def post(self, request, cohort_id, activity_id, submission_id):
        cohort = _get_cohort_and_validate_tutor(cohort_id, request.user)
        try:
            submission = StudentActivitySubmission.objects.get(
                id=submission_id,
                activity_id=activity_id,
                activity__cohort=cohort,
                is_deleted=False,
            )
        except StudentActivitySubmission.DoesNotExist:
            raise NotFound("Submission not found.")

        serializer = GradeSubmissionPayloadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        graded = CohortActivityService.grade_submission(
            submission=submission,
            score=serializer.validated_data["score"],
            feedback=serializer.validated_data.get("feedback", ""),
            tutor=request.user,
        )

        resp_serializer = StudentActivitySubmissionSerializer(graded)
        return self.success_response(
            data=resp_serializer.data,
            message="Submission graded successfully.",
        )


class StudentCohortActivitiesListView(SuccessResponseMixin, APIView):
    """
    GET /api/v1/lms/cohorts/<uuid:cohort_id>/activities/
    Student views activities of their cohort with submission status.
    """

    permission_classes = [IsStudentOrStaff]

    def get(self, request, cohort_id=None):
        user = request.user
        if cohort_id:
            try:
                cohort = Cohort.objects.get(id=cohort_id)
            except Cohort.DoesNotExist:
                raise NotFound("Cohort not found.")

            if user.role == UserRole.STUDENT and not cohort.students.filter(id=user.id).exists():
                raise PermissionDenied("You are not enrolled in this cohort.")
            cohort_qs = [cohort]
        else:
            cohort_qs = user.enrolled_cohorts.filter(is_active=True)
            if not cohort_qs.exists():
                return self.success_response(data=[])

        course_id = request.query_params.get("course_id")
        qs = CohortActivity.objects.filter(cohort__in=cohort_qs, is_published=True, is_deleted=False)
        if course_id:
            qs = qs.filter(course_id=course_id)

        # Attach student submission if exists
        submissions = {
            s.activity_id: s
            for s in StudentActivitySubmission.objects.filter(student=user, activity__in=qs)
        }

        results = []
        for act in qs:
            sub = submissions.get(act.id)
            results.append({
                "id": str(act.id),
                "title": act.title,
                "title_kinyarwanda": act.title_kinyarwanda,
                "description": act.description,
                "description_kinyarwanda": act.description_kinyarwanda,
                "activity_type": act.activity_type,
                "submission_type": act.submission_type,
                "total_points": act.total_points,
                "passing_points": act.passing_points,
                "due_date": act.due_date,
                "is_locked": act.is_locked,
                "submission": (
                    StudentActivitySubmissionSerializer(sub).data if sub else None
                ),
            })

        return self.success_response(data=results)


class StudentCohortActivitySubmitView(SuccessResponseMixin, APIView):
    """
    POST /api/v1/lms/cohorts/<uuid:cohort_id>/activities/<uuid:activity_id>/submit/
    Student submits homework/practical task.
    """

    permission_classes = [IsStudentOrStaff]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request, cohort_id, activity_id):
        user = request.user
        try:
            cohort = Cohort.objects.get(id=cohort_id)
        except Cohort.DoesNotExist:
            raise NotFound("Cohort not found.")

        try:
            activity = CohortActivity.objects.get(id=activity_id, cohort=cohort, is_deleted=False)
        except CohortActivity.DoesNotExist:
            raise NotFound("Activity not found.")

        submission_text = request.data.get("submission_text", "")
        attachment = request.FILES.get("attachment")

        submission = CohortActivityService.submit_activity(
            activity=activity,
            student=user,
            submission_text=submission_text,
            attachment=attachment,
        )

        resp_serializer = StudentActivitySubmissionSerializer(submission)
        return self.created_response(
            data=resp_serializer.data,
            message="Activity submission received successfully.",
        )
