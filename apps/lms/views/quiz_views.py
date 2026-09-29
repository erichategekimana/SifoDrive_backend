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

from rest_framework import generics, permissions
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.views import APIView

from apps.core.mixins import SuccessResponseMixin, SoftDeleteMixin
from apps.core.pagination import LargeBatchPagination
from apps.accounts.constants import UserRole
from apps.lms.models import Quiz, QuizQuestion
from apps.lms.serializers import (
    QuizDetailSerializer,
    QuizListSerializer,
    QuizQuestionDetailSerializer,
    QuizQuestionListSerializer,
    QuizQuestionWriteSerializer,
    QuizWriteSerializer,
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

        if not _is_content_staff(user):
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
        status_filter = request.query_params.get("status")
        if status_filter:
            filtered = [q for q in queryset if q.status.lower() == status_filter.lower()]
            return self.success_response(data=QuizListSerializer(filtered, many=True).data)
        return self.success_response(data=self.get_serializer(queryset, many=True).data)

    def create(self, request, *args, **kwargs):
        if not _is_admin(request.user):
            raise PermissionDenied("Only administrators can create quizzes.")
        serializer = QuizWriteSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        quiz = serializer.save()
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
            return self.get_queryset().get(pk=self.kwargs["pk"])
        except Quiz.DoesNotExist:
            raise NotFound("Quiz not found.")

    def retrieve(self, request, *args, **kwargs):
        return self.success_response(data=QuizDetailSerializer(self.get_object()).data)

    def patch(self, request, *args, **kwargs):
        if not _is_admin(request.user):
            raise PermissionDenied("Only administrators can update quizzes.")
        quiz = self.get_object()
        serializer = QuizWriteSerializer(
            quiz, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        quiz = serializer.save()
        return self.success_response(
            data=QuizDetailSerializer(quiz).data,
            message="Quiz updated successfully.",
        )

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
