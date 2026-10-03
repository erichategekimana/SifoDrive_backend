"""
apps/lms/views/cohort_material_views.py
=======================================
Views for Tutors managing cohort-specific module releases and quiz scheduling.
"""

from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.views import APIView

from apps.accounts.constants import UserRole
from apps.core.mixins import SuccessResponseMixin
from apps.core.permissions import IsStaffOrAdmin
from apps.live_classes.models import Cohort
from apps.lms.models import (
    Course,
    Module,
    Quiz,
    CohortActivity,
    CohortModuleRelease,
    CohortQuizSchedule,
    TutorCourseAssignment,
)
from apps.lms.serializers.cohort_content_serializers import (
    CohortModuleReleaseSerializer,
    CohortQuizScheduleSerializer,
    ExtendQuizDeadlinePayloadSerializer,
    ScheduleQuizPayloadSerializer,
    UpdateCohortModuleReleaseSerializer,
)
from apps.lms.services import CohortMaterialService


def _get_cohort_and_validate_access(cohort_id, user):
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


class TutorAssignedCohortsListView(SuccessResponseMixin, APIView):
    """
    GET /api/v1/lms/tutor/cohorts/
    Returns all cohorts assigned to the requesting tutor (or all cohorts for admins).
    """

    permission_classes = [IsStaffOrAdmin]

    def get(self, request):
        user = request.user
        if user.role in (UserRole.SYSTEM_ADMIN, UserRole.TRAINING_ADMIN) or user.is_superuser:
            cohorts = Cohort.objects.filter(is_active=True).order_by("-start_date")
        else:
            cohorts = user.assigned_cohorts.filter(is_active=True).order_by("-start_date")

        data = [
            {
                "id": str(c.id),
                "name": c.name,
                "code": c.code,
                "identifier": c.identifier or "",
                "status": c.status,
                "student_count": c.students.count(),
                "max_capacity": c.max_capacity,
                "schedule_description": c.schedule_description or "",
                "start_date": c.start_date,
                "end_date": c.end_date,
            }
            for c in cohorts
        ]
        return self.success_response(data=data)


class TutorCohortCoursesListView(SuccessResponseMixin, APIView):
    """
    GET /api/v1/lms/tutor/cohorts/<uuid:cohort_id>/courses/
    Returns courses taught in this cohort by this tutor (or all assigned cohort courses for admins).
    """

    permission_classes = [IsStaffOrAdmin]

    def get(self, request, cohort_id):
        cohort = _get_cohort_and_validate_access(cohort_id, request.user)
        user = request.user

        if user.role in (UserRole.SYSTEM_ADMIN, UserRole.TRAINING_ADMIN) or user.is_superuser:
            cohort_tutors = cohort.assigned_tutors.all()
            courses = Course.objects.filter(
                tutor_assignments__tutor__in=cohort_tutors,
                tutor_assignments__is_active=True,
                is_deleted=False,
            ).distinct()
        else:
            courses = Course.objects.filter(
                tutor_assignments__tutor=user,
                tutor_assignments__is_active=True,
                is_deleted=False,
            ).distinct()

        data = [
            {
                "id": str(c.id),
                "title": c.title,
                "title_kinyarwanda": c.title_kinyarwanda,
                "code": c.code,
                "curriculum_id": str(c.curriculum_id) if c.curriculum_id else None,
                "curriculum_title": c.curriculum.title if c.curriculum else "",
                "is_published": c.is_published,
                "module_count": c.modules.filter(is_deleted=False).count(),
            }
            for c in courses
        ]
        return self.success_response(data=data)


class TutorCohortModulesView(SuccessResponseMixin, APIView):
    """
    GET: List modules for a course with cohort-specific release & lock states.
    """

    permission_classes = [IsStaffOrAdmin]

    def get(self, request, cohort_id, course_id):
        cohort = _get_cohort_and_validate_access(cohort_id, request.user)
        try:
            course = Course.objects.get(id=course_id, is_deleted=False)
        except Course.DoesNotExist:
            raise NotFound("Course not found.")

        modules = course.modules.filter(is_deleted=False).order_by("sort_order")
        releases = {
            r.module_id: r
            for r in CohortModuleRelease.objects.filter(cohort=cohort, module__in=modules)
        }

        results = []
        for m in modules:
            rel = releases.get(m.id)
            results.append({
                "module_id": str(m.id),
                "title": m.title,
                "sort_order": m.sort_order,
                "is_foundational": m.is_foundational,
                "is_student_only": m.is_student_only,
                "is_course_published": m.is_published,
                "is_published_to_cohort": rel.is_published if rel else True,
                "is_locked_for_cohort": rel.is_locked if rel else False,
                "unlock_date": rel.unlock_date if rel else None,
            })

        return self.success_response(data=results)


class TutorCohortModuleReleaseUpdateView(SuccessResponseMixin, APIView):
    """
    PATCH /api/v1/lms/tutor/cohorts/<uuid:cohort_id>/modules/<uuid:module_id>/release/
    Updates cohort module release and lock status.
    """

    permission_classes = [IsStaffOrAdmin]

    def patch(self, request, cohort_id, module_id):
        cohort = _get_cohort_and_validate_access(cohort_id, request.user)
        try:
            module = Module.objects.get(id=module_id, is_deleted=False)
        except Module.DoesNotExist:
            raise NotFound("Module not found.")

        serializer = UpdateCohortModuleReleaseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        rel = CohortMaterialService.update_cohort_module_release(
            cohort=cohort,
            module=module,
            is_published=serializer.validated_data["is_published"],
            is_locked=serializer.validated_data.get("is_locked", False),
            unlock_date=serializer.validated_data.get("unlock_date"),
            user=request.user,
        )

        resp_serializer = CohortModuleReleaseSerializer(rel)
        return self.success_response(
            data=resp_serializer.data,
            message=f"Module '{module.title}' settings updated for cohort '{cohort.name}'.",
        )


class TutorCohortQuizzesView(SuccessResponseMixin, APIView):
    """
    GET /api/v1/lms/tutor/cohorts/<uuid:cohort_id>/courses/<uuid:course_id>/quizzes/
    Lists all course quizzes with their cohort-specific schedule and status.
    """

    permission_classes = [IsStaffOrAdmin]

    def get(self, request, cohort_id, course_id):
        cohort = _get_cohort_and_validate_access(cohort_id, request.user)
        try:
            course = Course.objects.get(id=course_id, is_deleted=False)
        except Course.DoesNotExist:
            raise NotFound("Course not found.")

        quizzes = course.quizzes.filter(is_deleted=False).order_by("-created_at")
        schedules = {
            s.quiz_id: s
            for s in CohortQuizSchedule.objects.filter(cohort=cohort, quiz__in=quizzes)
        }

        results = []
        for q in quizzes:
            sch = schedules.get(q.id)
            effective_deadline = (sch.extended_deadline or sch.deadline) if sch else q.deadline
            results.append({
                "quiz_id": str(q.id),
                "title": q.title,
                "title_kinyarwanda": q.title_kinyarwanda,
                "module_id": str(q.module_id) if q.module_id else None,
                "total_score": q.total_score,
                "passing_score": q.passing_score,
                "allow_tutor_scheduling": q.allow_tutor_scheduling,
                "is_published_to_cohort": sch.is_published if sch else q.is_published,
                "is_locked_for_cohort": sch.is_locked if sch else False,
                "open_date": sch.open_date if sch else q.open_date,
                "deadline": sch.deadline if sch else q.deadline,
                "extended_deadline": sch.extended_deadline if sch else None,
                "effective_deadline": effective_deadline,
                "extension_reason": sch.extension_reason if sch else "",
                "status_for_cohort": sch.status_for_cohort if sch else q.status,
            })

        return self.success_response(data=results)


class TutorCohortQuizScheduleView(SuccessResponseMixin, APIView):
    """
    POST /api/v1/lms/tutor/cohorts/<uuid:cohort_id>/quizzes/<uuid:quiz_id>/schedule/
    Schedules, publishes, or locks a quiz for this specific cohort.
    """

    permission_classes = [IsStaffOrAdmin]

    def post(self, request, cohort_id, quiz_id):
        cohort = _get_cohort_and_validate_access(cohort_id, request.user)
        try:
            quiz = Quiz.objects.get(id=quiz_id, is_deleted=False)
        except Quiz.DoesNotExist:
            raise NotFound("Quiz not found.")

        serializer = ScheduleQuizPayloadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        sch = CohortMaterialService.schedule_cohort_quiz(
            cohort=cohort,
            quiz=quiz,
            open_date=serializer.validated_data.get("open_date"),
            deadline=serializer.validated_data.get("deadline"),
            is_published=serializer.validated_data.get("is_published", True),
            is_locked=serializer.validated_data.get("is_locked", False),
            user=request.user,
        )

        resp_serializer = CohortQuizScheduleSerializer(sch)
        return self.success_response(
            data=resp_serializer.data,
            message=f"Quiz '{quiz.title}' schedule updated for cohort '{cohort.name}'.",
        )


class TutorCohortQuizExtendView(SuccessResponseMixin, APIView):
    """
    POST /api/v1/lms/tutor/cohorts/<uuid:cohort_id>/quizzes/<uuid:quiz_id>/extend/
    Extends a quiz deadline for this specific cohort with an optional reason.
    """

    permission_classes = [IsStaffOrAdmin]

    def post(self, request, cohort_id, quiz_id):
        cohort = _get_cohort_and_validate_access(cohort_id, request.user)
        try:
            quiz = Quiz.objects.get(id=quiz_id, is_deleted=False)
        except Quiz.DoesNotExist:
            raise NotFound("Quiz not found.")

        serializer = ExtendQuizDeadlinePayloadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        sch = CohortMaterialService.extend_cohort_quiz_deadline(
            cohort=cohort,
            quiz=quiz,
            extended_deadline=serializer.validated_data["extended_deadline"],
            reason=serializer.validated_data.get("reason", ""),
            user=request.user,
        )

        resp_serializer = CohortQuizScheduleSerializer(sch)
        return self.success_response(
            data=resp_serializer.data,
            message=f"Quiz deadline extended for cohort '{cohort.name}'.",
        )


class TutorApproachingDeadlinesView(SuccessResponseMixin, APIView):
    """
    GET /api/v1/lms/tutor/deadlines/
    Returns approaching deadlines (quizzes and activities) across the tutor's assigned cohorts directly from DB.
    """

    permission_classes = [IsStaffOrAdmin]

    def get(self, request):
        user = request.user
        if user.role in (UserRole.SYSTEM_ADMIN, UserRole.TRAINING_ADMIN) or user.is_superuser:
            cohort_ids = list(Cohort.objects.filter(is_active=True).values_list("id", flat=True))
        else:
            cohort_ids = list(user.assigned_cohorts.filter(is_active=True).values_list("id", flat=True))

        items = []

        # 1. Activities with deadlines
        activities = (
            CohortActivity.objects.filter(
                cohort_id__in=cohort_ids, is_deleted=False, is_published=True, due_date__isnull=False
            )
            .select_related("cohort", "course")
            .order_by("due_date")
        )

        for act in activities:
            items.append({
                "id": str(act.id),
                "type": "ACTIVITY",
                "title": act.title,
                "cohort_name": act.cohort.name if act.cohort else "Cohort",
                "cohort_identifier": getattr(act.cohort, "identifier", "") if act.cohort else "",
                "course_title": act.course.title if act.course else "",
                "due_date": act.due_date.isoformat() if act.due_date else None,
                "submission_count": act.submissions.count(),
                "graded_count": act.submissions.filter(status="GRADED").count(),
            })

        # 2. Quiz schedules with deadlines
        quiz_schedules = (
            CohortQuizSchedule.objects.filter(
                cohort_id__in=cohort_ids, is_published=True, deadline__isnull=False
            )
            .select_related("cohort", "quiz", "quiz__course")
            .order_by("deadline")
        )

        for qs in quiz_schedules:
            effective_deadline = qs.extended_deadline or qs.deadline
            items.append({
                "id": str(qs.id),
                "type": "QUIZ",
                "title": qs.quiz.title if qs.quiz else "Quiz",
                "cohort_name": qs.cohort.name if qs.cohort else "Cohort",
                "cohort_identifier": getattr(qs.cohort, "identifier", "") if qs.cohort else "",
                "course_title": qs.quiz.course.title if (qs.quiz and qs.quiz.course) else "",
                "due_date": effective_deadline.isoformat() if effective_deadline else None,
                "extended_deadline": qs.extended_deadline.isoformat() if qs.extended_deadline else None,
                "is_extended": bool(qs.extended_deadline),
                "submission_count": 0,
                "graded_count": 0,
            })

        # Sort all items chronologically by due_date
        items.sort(key=lambda x: x["due_date"] or "")

        return self.success_response(data=items)

