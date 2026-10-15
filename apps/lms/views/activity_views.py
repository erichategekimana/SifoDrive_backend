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
    GET: List activities for a cohort (or all cohorts for course if admin).
    POST: Create a new activity for a cohort or multiple/all cohorts (Tutor & Admin).
    """

    permission_classes = [IsStaffOrAdmin]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request, cohort_id):
        cohort = _get_cohort_and_validate_tutor(cohort_id, request.user)
        course_id = request.query_params.get("course_id")
        show_all = (
            request.query_params.get("all_cohorts") == "true"
            or request.user.role in (UserRole.SYSTEM_ADMIN, UserRole.TRAINING_ADMIN)
        )
        if show_all and course_id:
            qs = CohortActivity.objects.filter(
                course_id=course_id, is_deleted=False
            ).select_related("cohort", "course", "created_by")
        else:
            qs = CohortActivity.objects.filter(
                cohort=cohort, is_deleted=False
            ).select_related("cohort", "course", "created_by")
            if course_id:
                qs = qs.filter(course_id=course_id)

        serializer = CohortActivitySerializer(qs, many=True, context={"request": request})
        return self.success_response(data=serializer.data)

    def post(self, request, cohort_id):
        cohort = _get_cohort_and_validate_tutor(cohort_id, request.user)
        req_data = request.data.copy() if hasattr(request.data, "copy") else dict(request.data)
        if "cohort" not in req_data or not req_data["cohort"]:
            req_data["cohort"] = str(cohort.id)
        if ("course" not in req_data or not req_data["course"]) and getattr(cohort, "course", None):
            req_data["course"] = str(cohort.course.id)
        serializer = CohortActivitySerializer(data=req_data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        course = data["course"]
        module = data.get("module")

        target_type = request.data.get("target_type", "SINGLE_COHORT")
        target_cohort_ids = request.data.get("target_cohort_ids", [])
        if isinstance(target_cohort_ids, str):
            import json
            try:
                target_cohort_ids = json.loads(target_cohort_ids)
            except Exception:
                target_cohort_ids = [c.strip() for c in target_cohort_ids.split(",") if c.strip()]

        # Determine cohorts to create for
        cohorts_to_target = [cohort]
        if target_type == "ALL_COHORTS":
            if request.user.role in (UserRole.SYSTEM_ADMIN, UserRole.TRAINING_ADMIN):
                cohorts_to_target = list(Cohort.objects.filter(is_active=True))
            else:
                cohorts_to_target = list(request.user.assigned_cohorts.filter(is_active=True))
            if not cohorts_to_target:
                cohorts_to_target = [cohort]
        elif target_type == "MULTIPLE_COHORTS" and target_cohort_ids:
            found_cohorts = Cohort.objects.filter(id__in=target_cohort_ids, is_active=True)
            if found_cohorts.exists():
                cohorts_to_target = list(found_cohorts)

        allowed_methods = data.get("allowed_submission_methods", [])
        if isinstance(allowed_methods, str):
            import json
            try:
                allowed_methods = json.loads(allowed_methods)
            except Exception:
                allowed_methods = [m.strip() for m in allowed_methods.split(",") if m.strip()]

        created_activities = []
        for c in cohorts_to_target:
            activity = CohortActivityService.create_activity(
                cohort=c,
                course=course,
                module=module,
                title=data["title"],
                description=data["description"],
                title_kinyarwanda=data.get("title_kinyarwanda", ""),
                description_kinyarwanda=data.get("description_kinyarwanda", ""),
                activity_type=data.get("activity_type", "ASSIGNMENT"),
                submission_type=data.get("submission_type", "TEXT_RESPONSE"),
                allowed_submission_methods=allowed_methods or ["text"],
                resource_type=data.get("resource_type", "TEXT"),
                attachment=request.FILES.get("attachment") or data.get("attachment"),
                attachment_url=data.get("attachment_url", ""),
                total_points=data.get("total_points", 100),
                passing_points=data.get("passing_points", 70),
                open_date=data.get("open_date"),
                due_date=data.get("due_date"),
                allow_late_submission=data.get("allow_late_submission", False),
                is_published=data.get("is_published", True),
                is_locked=data.get("is_locked", False),
                release_grades_immediately=data.get("release_grades_immediately", False),
                tutor=request.user,
            )
            created_activities.append(activity)

        primary_activity = created_activities[0]
        resp_serializer = CohortActivitySerializer(primary_activity, context={"request": request})
        return self.created_response(
            data=resp_serializer.data,
            message=f"Activity '{primary_activity.title}' created successfully across {len(created_activities)} cohort(s).",
        )


class TutorCohortActivityDetailUpdateDeleteView(SuccessResponseMixin, APIView):
    """
    GET, PATCH, DELETE a specific cohort activity.
    """

    permission_classes = [IsStaffOrAdmin]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_object(self, cohort_id, activity_id, user):
        if user.role in (UserRole.SYSTEM_ADMIN, UserRole.TRAINING_ADMIN) or user.is_superuser:
            try:
                return CohortActivity.objects.get(id=activity_id, is_deleted=False)
            except CohortActivity.DoesNotExist:
                raise NotFound("Activity not found.")
        cohort = _get_cohort_and_validate_tutor(cohort_id, user)
        try:
            return CohortActivity.objects.get(id=activity_id, cohort=cohort, is_deleted=False)
        except CohortActivity.DoesNotExist:
            raise NotFound("Activity not found.")

    def get(self, request, cohort_id, activity_id):
        activity = self.get_object(cohort_id, activity_id, request.user)
        return self.success_response(data=CohortActivitySerializer(activity, context={"request": request}).data)

    def patch(self, request, cohort_id, activity_id):
        activity = self.get_object(cohort_id, activity_id, request.user)
        serializer = CohortActivitySerializer(activity, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = serializer.save()

        # Handle attachment file if uploaded
        if "attachment" in request.FILES:
            updated.attachment = request.FILES["attachment"]
            updated.save(update_fields=["attachment", "updated_at"])

        return self.success_response(
            data=CohortActivitySerializer(updated, context={"request": request}).data,
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
        serializer = StudentActivitySubmissionSerializer(submissions, many=True, context={"request": request})
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

        resp_serializer = StudentActivitySubmissionSerializer(graded, context={"request": request})
        return self.success_response(
            data=resp_serializer.data,
            message="Submission graded successfully.",
        )


class TutorCohortActivityPublishGradesView(SuccessResponseMixin, APIView):
    """
    POST /api/v1/lms/tutor/cohorts/<uuid:cohort_id>/activities/<uuid:activity_id>/publish-grades/
    Publishes activity scores/points to cohort students.
    """

    permission_classes = [IsStaffOrAdmin]

    def post(self, request, cohort_id, activity_id):
        cohort = _get_cohort_and_validate_tutor(cohort_id, request.user)
        try:
            activity = CohortActivity.objects.get(
                id=activity_id, cohort=cohort, is_deleted=False
            )
        except CohortActivity.DoesNotExist:
            raise NotFound("Activity not found.")

        activity = CohortActivityService.publish_grades(activity)

        return self.success_response(
            data=CohortActivitySerializer(activity, context={"request": request}).data,
            message=f"Grades for activity '{activity.title}' published successfully to cohort students.",
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
        qs = CohortActivity.objects.filter(
            cohort__in=cohort_qs, is_published=True, is_deleted=False
        ).select_related("cohort", "course", "module", "created_by")
        if user.role == UserRole.STUDENT:
            qs = qs.filter(is_locked=False)
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
            act_dict = CohortActivitySerializer(act, context={"request": request}).data
            if sub:
                sub_data = StudentActivitySubmissionSerializer(sub, context={"request": request}).data
                # Points are only available to the student once published by the tutor or set to immediate release,
                # AND only after the open date and deadline have passed.
                is_dates_pending = (
                    (act.open_date and act.open_date > timezone.now()) or
                    (act.due_date and act.due_date > timezone.now())
                )
                if user.role == UserRole.STUDENT and (
                    is_dates_pending or not (act.grades_published or getattr(act, "release_grades_immediately", False))
                ):
                    sub_data["score"] = None
                    sub_data["tutor_feedback"] = ""
                    sub_data["is_score_published"] = False
                else:
                    sub_data["is_score_published"] = True
                act_dict["submission"] = sub_data
            else:
                act_dict["submission"] = None
            results.append(act_dict)

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

        submission_text = (
            request.data.get("submission_text")
            or request.data.get("text_content")
            or ""
        )
        submission_link = (
            request.data.get("submission_link")
            or request.data.get("link")
            or ""
        )
        submission_method = request.data.get("submission_method", "TEXT")
        attachment = (
            request.FILES.get("attachment")
            or request.FILES.get("attachment_file")
            or request.FILES.get("file")
        )

        submission = CohortActivityService.submit_activity(
            activity=activity,
            student=user,
            submission_text=submission_text,
            attachment=attachment,
            submission_link=submission_link,
            submission_method=submission_method,
        )

        resp_serializer = StudentActivitySubmissionSerializer(submission, context={"request": request})
        return self.created_response(
            data=resp_serializer.data,
            message="Activity submission received successfully.",
        )
