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
        cohort = Cohort.objects.get(id=cohort_id, is_active=True)
    except Cohort.DoesNotExist:
        raise NotFound("Active cohort not found.")

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
    Returns active cohorts assigned to the requesting tutor (or all active cohorts for admins).
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


class TutorCohortStudentsListView(SuccessResponseMixin, APIView):
    """
    GET /api/v1/lms/tutor/cohorts/<uuid:cohort_id>/students/
    Returns active enrolled students for a cohort assigned to the requesting tutor (or admin).
    """

    permission_classes = [IsStaffOrAdmin]

    def get(self, request, cohort_id):
        cohort = _get_cohort_and_validate_access(cohort_id, request.user)
        students = cohort.students.filter(is_active=True).order_by("first_name", "last_name", "phone_number")

        data = [
            {
                "id": str(s.id),
                "name": s.get_full_name() or s.phone_number,
                "first_name": s.first_name,
                "last_name": s.last_name,
                "student_id": s.student_id or f"SF-{str(s.id)[:8].upper()}",
                "phone_number": s.phone_number,
                "email": s.email or "",
                "category": getattr(s, "station_quota", None) or "General Road Rules",
                "enrolled_at": s.created_at,
            }
            for s in students
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
            # By default, modules are locked for cohorts until the tutor explicitly unlocks/releases them
            is_published = rel.is_published if rel else False
            is_locked = rel.is_locked if rel else True
            results.append({
                "id": str(m.id),
                "module_id": str(m.id),
                "title": m.title,
                "sort_order": m.sort_order,
                "order": m.sort_order,
                "is_foundational": m.is_foundational,
                "is_student_only": m.is_student_only,
                "is_course_published": m.is_published,
                "is_default_published": m.is_published,
                "is_published": is_published,
                "is_locked": is_locked,
                "is_published_to_cohort": is_published,
                "is_locked_for_cohort": is_locked,
                "unlock_date": rel.unlock_date if rel else None,
                "lessons_count": m.lessons.filter(is_deleted=False).count(),
            })

        return self.success_response(data=results)


class TutorCohortModuleReleaseUpdateView(SuccessResponseMixin, APIView):
    """
    PATCH /api/v1/lms/tutor/cohorts/<uuid:cohort_id>/modules/<uuid:module_id>/release/
    Updates cohort module release and lock status.
    """

    permission_classes = [IsStaffOrAdmin]

    def post(self, request, cohort_id, module_id):
        return self.patch(request, cohort_id, module_id)

    def patch(self, request, cohort_id, module_id):
        cohort = _get_cohort_and_validate_access(cohort_id, request.user)
        try:
            module = Module.objects.get(id=module_id, is_deleted=False)
        except Module.DoesNotExist:
            raise NotFound("Module not found.")

        serializer = UpdateCohortModuleReleaseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        is_locked = serializer.validated_data.get("is_locked", False)
        # If is_published was explicitly provided, use it; otherwise deduce from is_locked
        if "is_published" in serializer.validated_data:
            is_published = serializer.validated_data["is_published"]
        else:
            is_published = not is_locked

        rel = CohortMaterialService.update_cohort_module_release(
            cohort=cohort,
            module=module,
            is_published=is_published,
            is_locked=is_locked,
            unlock_date=serializer.validated_data.get("unlock_date"),
            user=request.user,
        )

        resp_serializer = CohortModuleReleaseSerializer(rel)
        return self.success_response(
            data=resp_serializer.data,
            message=f"Module '{module.title}' settings updated for cohort '{cohort.name}'.",
        )


def _is_admin(user) -> bool:
    return user.is_authenticated and (
        user.role in (UserRole.TRAINING_ADMIN, UserRole.SYSTEM_ADMIN) or user.is_superuser
    )


class TutorCohortQuizzesView(SuccessResponseMixin, APIView):
    """
    GET /api/v1/lms/tutor/cohorts/<uuid:cohort_id>/courses/<uuid:course_id>/quizzes/
    Lists all course quizzes with their cohort-specific schedule and status.
    Tutors should never see draft quizzes created by training or system admins.
    Those set to 'OPEN' are the ones tutors can control visibility for.
    """

    permission_classes = [IsStaffOrAdmin]

    def get(self, request, cohort_id, course_id):
        cohort = _get_cohort_and_validate_access(cohort_id, request.user)
        try:
            course = Course.objects.get(id=course_id, is_deleted=False)
        except Course.DoesNotExist:
            raise NotFound("Course not found.")

        # Tutors should never see draft quizzes created by training/system admins.
        # Published quizzes (OPEN, SCHEDULED, CLOSED) can have cohort visibility and schedules controlled by tutors.
        course_quizzes = course.quizzes.filter(is_deleted=False, is_published=True).order_by("-created_at")
        quizzes = [q for q in course_quizzes if q.status != "DRAFT"]
        schedules = {
            s.quiz_id: s
            for s in CohortQuizSchedule.objects.filter(cohort=cohort, quiz__in=quizzes)
        }

        results = []
        for q in quizzes:
            sch = schedules.get(q.id)
            effective_deadline = (sch.extended_deadline or sch.deadline) if sch else q.deadline
            # By default, a quiz is locked / unpublished for cohorts until the tutor unlocks/publishes it
            is_locked = sch.is_locked if sch else True
            is_published = sch.is_published if sch else False
            status_for_cohort = sch.status_for_cohort if sch else "LOCKED"

            results.append({
                "id": str(q.id),
                "quiz_id": str(q.id),
                "title": q.title,
                "title_kinyarwanda": q.title_kinyarwanda,
                "module_id": str(q.module_id) if q.module_id else None,
                "total_score": q.total_score,
                "passing_score": q.passing_score,
                "time_limit_minutes": q.time_limit_minutes,
                "max_attempts": q.max_attempts,
                "rubric": q.rubric,
                "rubric_kinyarwanda": q.rubric_kinyarwanda,
                "allow_tutor_scheduling": q.allow_tutor_scheduling,
                "allow_tutor_edit_instructions": q.allow_tutor_edit_instructions,
                "allow_tutor_edit_duration": q.allow_tutor_edit_duration,
                "allow_tutor_edit_attempts": q.allow_tutor_edit_attempts,
                "is_published": is_published,
                "is_locked": is_locked,
                "is_published_to_cohort": is_published,
                "is_locked_for_cohort": is_locked,
                "open_date": sch.open_date if sch else q.open_date,
                "deadline": sch.deadline if sch else q.deadline,
                "extended_deadline": sch.extended_deadline if sch else None,
                "effective_deadline": effective_deadline,
                "extension_reason": sch.extension_reason if sch else "",
                "status_for_cohort": status_for_cohort,
            })

        return self.success_response(data=results)


class TutorCohortQuizScheduleView(SuccessResponseMixin, APIView):
    """
    POST /api/v1/lms/tutor/cohorts/<uuid:cohort_id>/quizzes/<uuid:quiz_id>/schedule/
    Schedules, publishes, or locks a quiz for this specific cohort.
    Published quizzes (OPEN, SCHEDULED, CLOSED) are allowed to have cohort visibility managed by tutors.
    """

    permission_classes = [IsStaffOrAdmin]

    def post(self, request, cohort_id, quiz_id):
        cohort = _get_cohort_and_validate_access(cohort_id, request.user)
        try:
            quiz = Quiz.objects.get(id=quiz_id, is_deleted=False, is_published=True)
            if quiz.status == "DRAFT" and not _is_admin(request.user):
                raise PermissionDenied("Only published quizzes can have cohort visibility and scheduling controlled by tutors.")
        except Quiz.DoesNotExist:
            raise NotFound("Quiz not found.")

        serializer = ScheduleQuizPayloadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        sch = CohortMaterialService.schedule_cohort_quiz(
            cohort=cohort,
            quiz=quiz,
            open_date=serializer.validated_data.get("open_date"),
            deadline=serializer.validated_data.get("deadline"),
            closing_date=serializer.validated_data.get("closing_date"),
            allow_late_submission=serializer.validated_data.get("allow_late_submission", False),
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
        quiz_filter = {
            "cohort_id__in": cohort_ids,
            "is_published": True,
            "deadline__isnull": False,
        }
        if request.user.is_authenticated and request.user.role in (UserRole.STUDENT, UserRole.GUEST):
            quiz_filter["is_locked"] = False

        quiz_schedules = (
            CohortQuizSchedule.objects.filter(**quiz_filter)
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

