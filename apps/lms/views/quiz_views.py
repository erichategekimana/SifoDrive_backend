"""
apps/lms/views/quiz_views.py
==============================
Quiz bank (QuizQuestion) and Quiz management views.

Endpoints:
  GET       /lms/questions/           → QuizQuestionListView
  GET       /lms/questions/<id>/      → QuizQuestionDetailView
  POST      /lms/questions/           → QuizQuestionCreateView
  PATCH     /lms/questions/<id>/      → QuizQuestionUpdateView
  GET/POST  /lms/quizzes/             → QuizListCreateView
  GET/PATCH/DELETE /lms/quizzes/<id>/ → QuizDetailUpdateDeleteView
  POST      /lms/quizzes/<id>/publish/ → QuizPublishToggleView
"""

import logging
from django.db import models
from rest_framework import generics, permissions
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.views import APIView

logger = logging.getLogger(__name__)

from apps.core.mixins import SuccessResponseMixin, SoftDeleteMixin
from apps.core.pagination import LargeBatchPagination
from apps.accounts.constants import UserRole
from apps.live_classes.models import Cohort
from apps.lms.models import Quiz, QuizQuestion, CohortQuizSchedule, QuizSubmission, QuizType
from apps.lms.serializers import (
    QuizDetailSerializer,
    QuizListSerializer,
    QuizQuestionDetailSerializer,
    QuizQuestionListSerializer,
    QuizQuestionWriteSerializer,
    QuizWriteSerializer,
    QuizSubmissionSerializer,
)


def _is_content_staff(user) -> bool:
    return user.is_authenticated and user.role in (
        UserRole.TUTOR, UserRole.TRAINING_ADMIN, UserRole.SYSTEM_ADMIN
    )


def _is_admin(user) -> bool:
    return user.is_authenticated and user.role in (
        UserRole.TRAINING_ADMIN, UserRole.SYSTEM_ADMIN
    )


# ===========================================================================
# QUIZ QUESTION BANK VIEWS
# ===========================================================================

class QuizQuestionListView(SuccessResponseMixin, generics.ListAPIView):
    """
    GET /lms/questions/
    Question bank browser — Students, Tutors, Admins only.
    Correct answers are NOT exposed in this list view.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class   = QuizQuestionListSerializer
    pagination_class   = LargeBatchPagination
    filterset_fields   = ["domain", "difficulty", "is_active"]
    search_fields      = ["question_text", "question_text_kinyarwanda"]
    ordering_fields    = ["domain", "difficulty", "created_at"]
    ordering           = ["domain", "difficulty"]

    def get_queryset(self):
        if self.request.user.role not in (
            UserRole.STUDENT, UserRole.TUTOR, UserRole.TRAINING_ADMIN, UserRole.SYSTEM_ADMIN
        ):
            raise PermissionDenied("Quiz questions are only accessible to students and staff.")
        return QuizQuestion.objects.filter(is_active=True)


class QuizQuestionDetailView(SuccessResponseMixin, generics.RetrieveAPIView):
    """
    GET /lms/questions/<id>/
    Full question detail including correct answer.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class   = QuizQuestionDetailSerializer
    queryset           = QuizQuestion.objects.all()

    def get_object(self):
        if self.request.user.role not in (
            UserRole.STUDENT, UserRole.TUTOR, UserRole.TRAINING_ADMIN, UserRole.SYSTEM_ADMIN
        ):
            raise PermissionDenied("Quiz questions are only accessible to students and staff.")
        return super().get_object()


class QuizQuestionCreateView(SuccessResponseMixin, generics.CreateAPIView):
    """POST /lms/questions/ — Tutor+Admin only."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class   = QuizQuestionWriteSerializer

    def create(self, request, *args, **kwargs):
        if not _is_content_staff(request.user):
            raise PermissionDenied("Only tutors and administrators can create questions.")
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        question = serializer.save(created_by=request.user)
        return self.created_response(
            data=QuizQuestionDetailSerializer(question).data,
            message="Question added to the question bank.",
        )


class QuizQuestionUpdateView(SuccessResponseMixin, generics.UpdateAPIView):
    """PATCH /lms/questions/<id>/ — Tutor+Admin only."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class   = QuizQuestionWriteSerializer
    queryset           = QuizQuestion.objects.all()
    http_method_names  = ["patch"]

    def update(self, request, *args, **kwargs):
        if not _is_content_staff(request.user):
            raise PermissionDenied("Only tutors and administrators can edit questions.")
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return self.success_response(
            data=QuizQuestionDetailSerializer(serializer.instance).data,
            message="Question updated.",
        )


# ===========================================================================
# QUIZ MANAGEMENT VIEWS
# ===========================================================================

class QuizListCreateView(SuccessResponseMixin, generics.ListCreateAPIView):
    """
    GET  /lms/quizzes/ — List quizzes (filterable by course, module, status).
    POST /lms/quizzes/ — Create a new quiz (Training Admin or System Admin).
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        return QuizWriteSerializer if self.request.method == "POST" else QuizListSerializer

    def get_queryset(self):
        user = self.request.user
        qs = Quiz.objects.select_related(
            "course", "module", "created_by"
        ).prefetch_related("items").all()

        if not _is_admin(user):
            # Tutors, Students, and Guests cannot see drafts.
            # Drafts are strictly training admin and system admin drafts.
            qs = qs.filter(is_published=True)

        course_id = self.request.query_params.get("course")
        if course_id:
            qs = qs.filter(course_id=course_id)

        module_id = self.request.query_params.get("module")
        if module_id:
            qs = qs.filter(module_id=module_id)

        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(title__icontains=search)

        return qs

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        # Students and guests: strictly only get quizzes that their tutor has unlocked & published for their cohort.
        # A quiz being published by admins does not mean students get it; it is controlled by tutors per cohort.
        if request.user.is_authenticated and request.user.role in (UserRole.STUDENT, UserRole.GUEST):
            user = request.user
            enrolled_cohorts = user.enrolled_cohorts.filter(is_active=True)
            if not enrolled_cohorts.exists():
                enrolled_cohorts = user.enrolled_cohorts.all()
            if not enrolled_cohorts.exists():
                from apps.live_classes.models import Cohort
                default_cohort = Cohort.objects.filter(is_active=True).first()
                if default_cohort:
                    default_cohort.students.add(user)
                    enrolled_cohorts = user.enrolled_cohorts.all()

            enrolled_cohort_ids = list(enrolled_cohorts.values_list("id", flat=True))
            if not enrolled_cohort_ids:
                return self.success_response(data=[])

            # A student ONLY gets quizzes that their tutor has unlocked (is_locked=False) and published (is_published=True) for their cohort.
            unlocked_quiz_ids = set(
                CohortQuizSchedule.objects.filter(
                    cohort_id__in=enrolled_cohort_ids,
                    is_published=True,
                    is_locked=False,
                ).values_list("quiz_id", flat=True)
            )

            allowed_quizzes = [q for q in queryset if q.status != "DRAFT" and q.id in unlocked_quiz_ids]

            status_filter = request.query_params.get("status")
            if status_filter:
                allowed_quizzes = [q for q in allowed_quizzes if q.status.lower() == status_filter.lower()]

            return self.success_response(data=QuizListSerializer(allowed_quizzes, many=True, context={"request": request}).data)

        # Tutors see all non-draft quizzes that admins published, so they can manage/lock/unlock for their cohorts
        if request.user.is_authenticated and request.user.role == UserRole.TUTOR:
            non_drafts = [q for q in queryset if q.status != "DRAFT"]
            status_filter = request.query_params.get("status")
            if status_filter:
                non_drafts = [q for q in non_drafts if q.status.lower() == status_filter.lower()]
            return self.success_response(data=QuizListSerializer(non_drafts, many=True, context={"request": request}).data)

        status_filter = request.query_params.get("status")
        if status_filter:
            filtered = [q for q in queryset if q.status.lower() == status_filter.lower()]
            return self.success_response(data=QuizListSerializer(filtered, many=True, context={"request": request}).data)

        return self.success_response(data=self.get_serializer(queryset, many=True, context={"request": request}).data)

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def create(self, request, *args, **kwargs):
        if not _is_admin(request.user):
            raise PermissionDenied("Only administrators can create quizzes.")
        serializer = QuizWriteSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        quiz = serializer.save(created_by=request.user)
        return self.created_response(
            data=QuizDetailSerializer(quiz).data,
            message="Quiz created successfully.",
        )


class QuizDetailUpdateDeleteView(SoftDeleteMixin, SuccessResponseMixin, generics.RetrieveUpdateDestroyAPIView):
    """
    GET    /lms/quizzes/<id>/ — Retrieve quiz with questions and rubric.
    PATCH  /lms/quizzes/<id>/ — Update quiz and questions.
    DELETE /lms/quizzes/<id>/ — Delete quiz.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Quiz.objects.select_related(
            "course", "module", "created_by"
        ).prefetch_related("items", "items__original_question").all()

    def get_object(self):
        try:
            quiz = self.get_queryset().get(pk=self.kwargs["pk"])
            user = self.request.user
            if not _is_admin(user):
                if not quiz.is_published or quiz.status == "DRAFT":
                    raise NotFound("Quiz not found.")
                if user.is_authenticated and user.role in (UserRole.STUDENT, UserRole.GUEST):
                    enrolled_cohorts = user.enrolled_cohorts.filter(is_active=True)
                    if not enrolled_cohorts.exists():
                        enrolled_cohorts = user.enrolled_cohorts.all()
                    if not enrolled_cohorts.exists():
                        from apps.live_classes.models import Cohort
                        default_cohort = Cohort.objects.filter(is_active=True).first()
                        if default_cohort:
                            default_cohort.students.add(user)
                            enrolled_cohorts = user.enrolled_cohorts.all()
                    enrolled_cohort_ids = list(enrolled_cohorts.values_list("id", flat=True))
                    if not enrolled_cohort_ids:
                        raise NotFound("Quiz not found.")
                    is_unlocked = CohortQuizSchedule.objects.filter(
                        cohort_id__in=enrolled_cohort_ids,
                        quiz=quiz,
                        is_published=True,
                        is_locked=False,
                    ).exists()
                    if not is_unlocked:
                        raise PermissionDenied("This quiz is currently locked by your instructor.")
            return quiz
        except Quiz.DoesNotExist:
            raise NotFound("Quiz not found.")

    def retrieve(self, request, *args, **kwargs):
        return self.success_response(data=QuizDetailSerializer(self.get_object(), context={"request": request}).data)

    def patch(self, request, *args, **kwargs):
        quiz = self.get_object()
        user = request.user

        if _is_admin(user):
            serializer = QuizWriteSerializer(
                quiz, data=request.data, partial=True, context={"request": request}
            )
            serializer.is_valid(raise_exception=True)
            quiz = serializer.save()
            return self.success_response(
                data=QuizDetailSerializer(quiz).data,
                message="Quiz updated successfully.",
            )

        if user.is_authenticated and user.role == UserRole.TUTOR:
            # Check what fields this tutor is permitted to update for this quiz
            allowed_fields = set()
            if quiz.allow_tutor_edit_instructions:
                allowed_fields.update({"description", "description_kinyarwanda", "rubric", "rubric_kinyarwanda"})
            if quiz.allow_tutor_scheduling:
                allowed_fields.update({"open_date", "deadline", "closing_date", "allow_late_submission"})
            if quiz.allow_tutor_edit_duration:
                allowed_fields.update({"time_limit_minutes"})
            if quiz.allow_tutor_edit_attempts:
                allowed_fields.update({"max_attempts"})

            # Tutors can configure grade release policy (Manual vs Immediate)
            allowed_fields.add("release_grades_immediately")

            attempted_fields = set(request.data.keys())
            disallowed_fields = attempted_fields - allowed_fields
            if disallowed_fields:
                raise PermissionDenied(
                    f"Permission denied: you are not granted access to modify {', '.join(sorted(disallowed_fields))}."
                )

            if not allowed_fields:
                raise PermissionDenied("The administrator has not granted tutor update permissions for this quiz.")

            filtered_data = {k: v for k, v in request.data.items() if k in allowed_fields}
            serializer = QuizWriteSerializer(
                quiz, data=filtered_data, partial=True, context={"request": request}
            )
            serializer.is_valid(raise_exception=True)
            quiz = serializer.save()
            return self.success_response(
                data=QuizDetailSerializer(quiz).data,
                message="Quiz rules updated successfully.",
            )

        raise PermissionDenied("Only tutors and administrators can update quizzes.")

    def perform_destroy(self, instance):
        if not _is_admin(self.request.user):
            raise PermissionDenied("Only administrators can delete quizzes.")
        instance.delete()


class QuizPublishToggleView(SuccessResponseMixin, APIView):
    """POST /lms/quizzes/<id>/publish/ — Toggle published state of a quiz."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk, *args, **kwargs):
        if not _is_admin(request.user):
            raise PermissionDenied("Only administrators can publish quizzes.")
        try:
            quiz = Quiz.objects.get(pk=pk)
        except Quiz.DoesNotExist:
            raise NotFound("Quiz not found.")
        quiz.is_published = not quiz.is_published
        quiz.save(update_fields=["is_published", "updated_at"])
        msg = "Quiz published successfully." if quiz.is_published else "Quiz unpublished."
        return self.success_response(data=QuizDetailSerializer(quiz).data, message=msg)


class QuizPublishGradesView(SuccessResponseMixin, APIView):
    """
    POST /lms/quizzes/<id>/publish-grades/
    Tutor or admin manually publishes grades for this quiz so students can view results.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk, *args, **kwargs):
        if not _is_content_staff(request.user):
            raise PermissionDenied("Only tutors and administrators can publish quiz grades.")
        try:
            quiz = Quiz.objects.get(id=pk)
        except Quiz.DoesNotExist:
            raise NotFound("Quiz not found.")

        now = timezone.now()

        def _validate_quiz_dates(target_open, target_deadline, label=None):
            prefix = f"for {label} " if label else ""
            if target_open and target_open > now:
                formatted_open = target_open.strftime("%Y-%m-%d %H:%M")
                raise ValidationError(
                    f"Cannot publish quiz grades {prefix}before the open date ({formatted_open}). "
                    "The quiz has not opened yet."
                )
            if target_deadline and target_deadline > now:
                formatted_deadline = target_deadline.strftime("%Y-%m-%d %H:%M")
                raise ValidationError(
                    f"Cannot publish quiz grades {prefix}before the quiz deadline ({formatted_deadline}). "
                    "Students may still be taking the quiz."
                )

        cohort_id = request.data.get("cohort_id")
        if cohort_id:
            try:
                cohort = Cohort.objects.get(id=cohort_id)
                sched, _ = CohortQuizSchedule.objects.get_or_create(cohort=cohort, quiz=quiz)
                effective_open = sched.open_date or quiz.open_date
                effective_deadline = sched.deadline or quiz.deadline
                _validate_quiz_dates(effective_open, effective_deadline, f"cohort '{cohort.name}'")
                sched.grades_published = True
                sched.save(update_fields=["grades_published", "updated_at"])
            except Cohort.DoesNotExist:
                raise NotFound("Cohort not found.")
        else:
            if request.user.role == UserRole.TUTOR:
                tutor_cohorts = request.user.assigned_cohorts.filter(is_active=True)
                for c in tutor_cohorts:
                    sched, _ = CohortQuizSchedule.objects.get_or_create(cohort=c, quiz=quiz)
                    effective_open = sched.open_date or quiz.open_date
                    effective_deadline = sched.deadline or quiz.deadline
                    _validate_quiz_dates(effective_open, effective_deadline, f"cohort '{c.name}'")
                for c in tutor_cohorts:
                    sched, _ = CohortQuizSchedule.objects.get_or_create(cohort=c, quiz=quiz)
                    sched.grades_published = True
                    sched.save(update_fields=["grades_published", "updated_at"])
            else:
                _validate_quiz_dates(quiz.open_date, quiz.deadline)
                for sched in CohortQuizSchedule.objects.filter(quiz=quiz):
                    effective_open = sched.open_date or quiz.open_date
                    effective_deadline = sched.deadline or quiz.deadline
                    _validate_quiz_dates(effective_open, effective_deadline, f"cohort '{sched.cohort.name}'")
                CohortQuizSchedule.objects.filter(quiz=quiz).update(grades_published=True)

        return self.success_response(
            message=f"Grades for quiz '{quiz.title}' published successfully to students."
        )


# ===========================================================================
# QUIZ SUBMISSION & PROCTORING VIEWS
# ===========================================================================

class QuizSubmitView(SuccessResponseMixin, APIView):
    """
    POST /lms/quizzes/<id>/submit/
    Submits a quiz attempt (LIVE_TIMED or WORK_SUBMISSION).
    Enforces time limits, maximum attempts, and tab-switching proctoring violation logs.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk, *args, **kwargs):
        try:
            quiz = Quiz.objects.prefetch_related("items").get(pk=pk)
        except Quiz.DoesNotExist:
            raise NotFound("Quiz not found.")

        user = request.user
        if not _is_admin(user) and user.role in (UserRole.STUDENT, UserRole.GUEST):
            from django.utils import timezone
            now = timezone.now()
            effective_open = quiz.open_date

            enrolled_cohorts = user.enrolled_cohorts.filter(is_active=True)
            if not enrolled_cohorts.exists():
                enrolled_cohorts = user.enrolled_cohorts.all()
            if enrolled_cohorts.exists():
                enrolled_cohort_ids = list(enrolled_cohorts.values_list("id", flat=True))
                schedules = CohortQuizSchedule.objects.filter(
                    cohort_id__in=enrolled_cohort_ids,
                    quiz=quiz,
                )
                sch = schedules.filter(is_published=True, is_locked=False).first()
                if not sch and quiz.allow_tutor_scheduling:
                    raise PermissionDenied("Cannot submit: This quiz is currently locked by your instructor.")
                if sch and sch.open_date:
                    effective_open = sch.open_date

            if effective_open and effective_open > now:
                formatted_date = effective_open.strftime("%Y-%m-%d %H:%M")
                raise PermissionDenied(
                    f"This quiz is scheduled to open on {formatted_date}. You cannot take or submit this quiz before its open date."
                )

        # Check attempts limit
        prior_attempts = QuizSubmission.objects.filter(quiz=quiz, student=user).count()
        if quiz.max_attempts > 0 and prior_attempts >= quiz.max_attempts:
            raise PermissionDenied(
                f"You have already reached the maximum attempts ({quiz.max_attempts}) for this quiz."
            )

        attempt_number = prior_attempts + 1

        # Extract submitted payload
        student_answers = request.data.get("student_answers", {})
        if isinstance(student_answers, str):
            import json
            try:
                student_answers = json.loads(student_answers)
            except Exception:
                student_answers = {}

        work_submission_text = request.data.get("work_submission_text", "")
        work_submission_file = request.FILES.get("work_submission_file")

        time_spent_seconds = int(request.data.get("time_spent_seconds", 0) or 0)
        tab_switch_count = int(request.data.get("tab_switch_count", 0) or 0)
        proctoring_violations = request.data.get("proctoring_violations", [])
        if isinstance(proctoring_violations, str):
            import json
            try:
                proctoring_violations = json.loads(proctoring_violations)
            except Exception:
                proctoring_violations = []

        flagged_questions = request.data.get("flagged_questions") or request.data.get("flagged_for_review_questions", [])
        if isinstance(flagged_questions, str):
            import json
            try:
                flagged_questions = json.loads(flagged_questions)
            except Exception:
                flagged_questions = []

        is_flagged = False
        if quiz.quiz_type == QuizType.LIVE_TIMED and quiz.enable_proctoring:
            if tab_switch_count > quiz.max_tab_switches_allowed:
                is_flagged = True

        # Calculate scores if quiz has items
        items = list(quiz.items.all())
        earned_points = 0
        total_possible = quiz.calculated_total_points or quiz.total_score or 100

        if items:
            for item in items:
                student_choice = student_answers.get(str(item.id)) or student_answers.get(item.id)
                if student_choice and str(student_choice).upper() == item.correct_option.upper():
                    earned_points += item.points

        percentage = round((earned_points / total_possible * 100), 1) if total_possible > 0 else 0.0
        is_passed = percentage >= quiz.passing_score

        # Cohort linkage if available
        cohort = None
        cohort_id = request.data.get("cohort_id") or request.data.get("cohort")
        if cohort_id and str(cohort_id) not in ("undefined", "null", ""):
            cohort = Cohort.objects.filter(id=cohort_id, is_active=True).first() or Cohort.objects.filter(id=cohort_id).first()
        if not cohort and hasattr(user, "enrolled_cohorts"):
            cohort = user.enrolled_cohorts.filter(is_active=True).first() or user.enrolled_cohorts.first()

        is_auto_graded = bool(items or quiz.quiz_type == QuizType.LIVE_TIMED)
        auto_score = earned_points if is_auto_graded else None

        submission = QuizSubmission.objects.create(
            quiz=quiz,
            student=user,
            cohort=cohort,
            attempt_number=attempt_number,
            quiz_type=quiz.quiz_type,
            score=earned_points,
            total_score=total_possible,
            percentage=percentage,
            is_passed=is_passed,
            is_auto_graded=is_auto_graded,
            auto_score=auto_score,
            student_answers=student_answers,
            work_submission_text=work_submission_text,
            work_submission_file=work_submission_file,
            time_spent_seconds=time_spent_seconds,
            tab_switch_count=tab_switch_count,
            proctoring_violations=proctoring_violations,
            is_flagged=is_flagged,
            flagged_questions=flagged_questions,
        )

        return self.created_response(
            data=QuizSubmissionSerializer(submission, context={"request": request}).data,
            message="Quiz submitted successfully.",
        )


class QuizSubmissionListView(SuccessResponseMixin, generics.ListAPIView):
    """
    GET /lms/quizzes/<id>/submissions/
    Lists submissions for a quiz.
    - Staff (Tutors/Admins): see student submissions, filtered by cohort or assigned cohorts.
    - Students: see their own past attempts.
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = QuizSubmissionSerializer

    def get_queryset(self):
        quiz_id = self.kwargs["pk"]
        user = self.request.user
        qs = QuizSubmission.objects.filter(quiz_id=quiz_id).select_related("student", "quiz", "cohort")

        if user.role in (UserRole.STUDENT, UserRole.GUEST):
            qs = qs.filter(student=user)
        else:
            cohort_id = self.request.query_params.get("cohort_id")
            if cohort_id and str(cohort_id) not in ("undefined", "null", "all", ""):
                try:
                    import uuid
                    uuid.UUID(str(cohort_id))
                    qs = qs.filter(
                        models.Q(cohort_id=cohort_id) | models.Q(student__enrolled_cohorts__id=cohort_id)
                    ).distinct()
                except ValueError:
                    pass
            elif user.role == UserRole.TUTOR and not (user.is_superuser or user.role in (UserRole.SYSTEM_ADMIN, UserRole.TRAINING_ADMIN)):
                assigned_cohorts = user.assigned_cohorts.all()
                if assigned_cohorts.exists():
                    qs = qs.filter(
                        models.Q(cohort__in=assigned_cohorts)
                        | models.Q(student__enrolled_cohorts__in=assigned_cohorts)
                        | models.Q(quiz__created_by=user)
                        | models.Q(cohort__isnull=True)
                    ).distinct()

            flagged = self.request.query_params.get("is_flagged")
            if flagged is not None:
                qs = qs.filter(is_flagged=(flagged.lower() in ("true", "1")))

        return qs.order_by("-created_at")


class QuizSubmissionGradeView(SuccessResponseMixin, APIView):
    """
    POST /lms/quizzes/<id>/submissions/<submission_id>/grade/
    Tutor or Admin manually grades a QuizSubmission and records updated score and feedback.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk, submission_id):
        user = request.user
        if not _is_content_staff(user):
            raise PermissionDenied("Only tutors and administrators can grade quiz submissions.")

        try:
            submission = QuizSubmission.objects.select_related("quiz", "student", "cohort").get(id=submission_id, quiz_id=pk)
        except QuizSubmission.DoesNotExist:
            raise NotFound("Quiz submission not found.")

        # Ensure tutor is in charge of this student's cohort
        if user.role == UserRole.TUTOR and not (user.is_superuser or user.role in (UserRole.SYSTEM_ADMIN, UserRole.TRAINING_ADMIN)):
            assigned_cohort_ids = set(user.assigned_cohorts.values_list("id", flat=True))
            student_cohort_ids = set(submission.student.enrolled_cohorts.values_list("id", flat=True))
            is_in_charge = bool(
                not assigned_cohort_ids
                or (submission.cohort_id and submission.cohort_id in assigned_cohort_ids)
                or (assigned_cohort_ids & student_cohort_ids)
                or (submission.student.assigned_tutor_id == user.id)
                or (submission.quiz.created_by_id == user.id)
            )
            if not is_in_charge:
                raise PermissionDenied("You can only grade submissions for students in your assigned cohorts.")

        score = request.data.get("score")
        feedback = request.data.get("feedback", "")
        reason = request.data.get("reason", "")

        from django.utils import timezone
        old_score = submission.score
        was_auto_graded = bool(submission.is_auto_graded or submission.quiz.quiz_type == QuizType.LIVE_TIMED)

        if score is not None:
            new_score = int(score)
            if was_auto_graded or submission.auto_score is not None or old_score != new_score:
                submission.is_grade_overridden = True
                submission.grade_overridden_by = user
                submission.grade_overridden_at = timezone.now()
                if reason:
                    submission.grade_override_reason = reason
                if submission.auto_score is None:
                    submission.auto_score = old_score

            submission.score = new_score
            if submission.total_score > 0:
                submission.percentage = round((submission.score / submission.total_score) * 100, 1)
                submission.is_passed = submission.percentage >= submission.quiz.passing_score

        submission.feedback = feedback
        submission.graded_by = user
        submission.graded_at = timezone.now()
        submission.save()

        # Audit logging for manual grade changes
        if was_auto_graded or submission.is_grade_overridden:
            try:
                from apps.audit.services.audit_service import AuditService
                AuditService.log_quiz_grade_overridden(
                    tutor=user,
                    student=submission.student,
                    submission=submission,
                    old_score=old_score,
                    new_score=submission.score,
                    request=request,
                )
            except Exception as audit_err:
                logger.warning("Failed to record audit log for quiz grade override: %s", audit_err)

        return self.success_response(
            data=QuizSubmissionSerializer(submission, context={"request": request}).data,
            message="Quiz submission graded successfully.",
        )

