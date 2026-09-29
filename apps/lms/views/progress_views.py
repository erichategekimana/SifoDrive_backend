"""
apps/lms/views/progress_views.py
==================================
Student Progress and Bookmark API views.

Endpoints:
  GET  /lms/progress/          → ProgressListView
  POST /lms/progress/complete/ → MarkLessonCompleteView
  POST /lms/progress/quiz/     → RecordQuizAttemptView
  GET  /lms/progress/summary/  → ProgressSummaryView
  GET  /lms/bookmarks/         → BookmarkListView
  POST /lms/bookmarks/         → BookmarkCreateView
  DELETE /lms/bookmarks/<id>/  → BookmarkDeleteView
"""

from rest_framework import generics, permissions
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.views import APIView

from apps.core.mixins import SuccessResponseMixin, SoftDeleteMixin
from apps.accounts.constants import UserRole
from apps.lms.models import Lesson, LessonBookmark, StudentProgress
from apps.lms.serializers import (
    LessonBookmarkSerializer,
    MarkLessonCompleteSerializer,
    ProgressSummarySerializer,
    RecordQuizAttemptSerializer,
    StudentProgressSerializer,
)
from apps.lms.services import ContentGateService, ProgressService


class ProgressListView(SuccessResponseMixin, generics.ListAPIView):
    """GET /lms/progress/ — Authenticated student's completed lessons."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class   = StudentProgressSerializer
    filterset_fields   = ["is_completed", "lesson__lesson_type"]
    ordering           = ["-updated_at"]

    def get_queryset(self):
        return StudentProgress.objects.filter(
            student=self.request.user
        ).select_related("lesson__module__course")


class MarkLessonCompleteView(SuccessResponseMixin, APIView):
    """POST /lms/progress/complete/ — Mark a lesson as completed. Student role required."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        if request.user.role != UserRole.STUDENT:
            raise PermissionDenied("Only enrolled students can track lesson progress.")
        serializer = MarkLessonCompleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            lesson = Lesson.objects.get(pk=serializer.validated_data["lesson_id"])
        except Lesson.DoesNotExist:
            raise NotFound("Lesson not found.")
        if not ContentGateService.can_access_lesson(request.user, lesson):
            raise PermissionDenied("You do not have access to this lesson.")
        progress = ProgressService.mark_lesson_complete(
            student=request.user,
            lesson=lesson,
            time_spent_seconds=serializer.validated_data["time_spent_seconds"],
        )
        return self.success_response(
            data=StudentProgressSerializer(progress).data,
            message="Lesson marked as complete.",
        )


class RecordQuizAttemptView(SuccessResponseMixin, APIView):
    """POST /lms/progress/quiz/ — Record a quiz attempt result. Student role required."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        if request.user.role != UserRole.STUDENT:
            raise PermissionDenied("Only enrolled students can take quizzes.")
        serializer = RecordQuizAttemptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            lesson = Lesson.objects.get(
                pk=serializer.validated_data["lesson_id"],
                lesson_type="QUIZ",
            )
        except Lesson.DoesNotExist:
            raise NotFound("Quiz lesson not found.")
        if not ContentGateService.can_access_lesson(request.user, lesson):
            raise PermissionDenied("You do not have access to this quiz.")
        try:
            progress = ProgressService.record_quiz_attempt(
                student=request.user,
                lesson=lesson,
                score=serializer.validated_data["score"],
                time_spent_seconds=serializer.validated_data["time_spent_seconds"],
            )
        except ValueError as exc:
            raise ValidationError(str(exc))
        return self.success_response(
            data=StudentProgressSerializer(progress).data,
            message="Quiz attempt recorded.",
        )


class ProgressSummaryView(SuccessResponseMixin, APIView):
    """GET /lms/progress/summary/ — Overall progress dashboard data."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        summary = ProgressService.get_progress_summary(request.user)
        return self.success_response(
            data=ProgressSummarySerializer(summary).data,
            meta={"is_exam_eligible": summary["is_exam_eligible"]},
        )


class BookmarkListView(SuccessResponseMixin, generics.ListAPIView):
    """GET /lms/bookmarks/ — Current student's bookmarked lessons."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class   = LessonBookmarkSerializer
    ordering           = ["-created_at"]

    def get_queryset(self):
        return LessonBookmark.objects.filter(
            student=self.request.user
        ).select_related("lesson__module__course")


class BookmarkCreateView(SuccessResponseMixin, generics.CreateAPIView):
    """POST /lms/bookmarks/ — Bookmark a lesson."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class   = LessonBookmarkSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        lesson = serializer.validated_data["lesson"]
        if not ContentGateService.can_access_lesson(request.user, lesson):
            raise PermissionDenied("You do not have access to this lesson.")
        try:
            bookmark = serializer.save()
        except Exception:
            raise ValidationError("You have already bookmarked this lesson.")
        return self.created_response(
            data=LessonBookmarkSerializer(bookmark).data,
            message="Lesson bookmarked.",
        )


class BookmarkDeleteView(SoftDeleteMixin, SuccessResponseMixin, generics.DestroyAPIView):
    """DELETE /lms/bookmarks/<id>/ — Remove a bookmark."""
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return LessonBookmark.objects.filter(student=self.request.user)

    def get_object(self):
        try:
            return self.get_queryset().get(pk=self.kwargs["pk"])
        except LessonBookmark.DoesNotExist:
            raise NotFound("Bookmark not found.")

    def perform_destroy(self, instance):
        instance.hard_delete()
