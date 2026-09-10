"""
apps/lms/views.py
==================
LMS API views.

All views are thin: they validate input, call a service method,
and return a response. No business logic lives here.

Permission summary:
  Public (AllowAny)         → none (LMS requires auth)
  Any authenticated user    → Course list, Road sign list
  Guest + Student           → Accessible lessons (respecting content flags)
  Student only              → Quiz questions, progress tracking, bookmarks
  Tutor + Admin             → Content creation and editing (draft state)
  Admin only                → Publish/unpublish, delete, course stats

Endpoint map:
  GET   /lms/courses/                → CourseListView
  POST  /lms/courses/                → CourseCreateView       (Tutor+Admin)
  GET   /lms/courses/<id>/           → CourseDetailView
  PATCH /lms/courses/<id>/           → CourseUpdateView       (Tutor+Admin)
  POST  /lms/courses/<id>/publish/   → CoursePublishView      (Admin)
  POST  /lms/courses/<id>/unpublish/ → CourseUnpublishView    (Admin)
  GET   /lms/courses/<id>/stats/     → CourseStatsView        (Tutor+Admin)
  DELETE /lms/courses/<id>/          → CourseDeleteView       (Admin)

  GET   /lms/courses/<id>/modules/   → ModuleListView
  POST  /lms/modules/                → ModuleCreateView       (Tutor+Admin)
  GET   /lms/modules/<id>/           → ModuleDetailView
  PATCH /lms/modules/<id>/           → ModuleUpdateView       (Tutor+Admin)
  POST  /lms/modules/<id>/publish/   → ModulePublishView      (Admin)
  POST  /lms/modules/<id>/unpublish/ → ModuleUnpublishView    (Admin)
  DELETE /lms/modules/<id>/          → ModuleDeleteView       (Admin)

  GET   /lms/modules/<id>/lessons/   → LessonListView
  POST  /lms/lessons/                → LessonCreateView       (Tutor+Admin)
  GET   /lms/lessons/<id>/           → LessonDetailView
  PATCH /lms/lessons/<id>/           → LessonUpdateView       (Tutor+Admin)
  DELETE /lms/lessons/<id>/          → LessonDeleteView       (Admin)
  POST  /lms/lessons/<id>/questions/ → LessonQuestionAddView  (Tutor+Admin)
  DELETE /lms/lessons/<id>/questions/<qid>/ → LessonQuestionRemoveView (Tutor+Admin)

  GET   /lms/road-signs/             → RoadSignListView
  POST  /lms/road-signs/             → RoadSignCreateView     (Tutor+Admin)
  GET   /lms/road-signs/<id>/        → RoadSignDetailView
  PATCH /lms/road-signs/<id>/        → RoadSignUpdateView     (Admin)

  GET   /lms/questions/              → QuizQuestionListView   (Student+)
  POST  /lms/questions/              → QuizQuestionCreateView (Tutor+Admin)
  GET   /lms/questions/<id>/         → QuizQuestionDetailView (Student+)
  PATCH /lms/questions/<id>/         → QuizQuestionUpdateView (Tutor+Admin)

  POST  /lms/progress/complete/      → MarkLessonCompleteView (Student)
  POST  /lms/progress/quiz/          → RecordQuizAttemptView  (Student)
  GET   /lms/progress/summary/       → ProgressSummaryView    (Student)
  GET   /lms/progress/               → ProgressListView       (Student)

  GET   /lms/bookmarks/              → BookmarkListView       (Student)
  POST  /lms/bookmarks/              → BookmarkCreateView     (Student)
  DELETE /lms/bookmarks/<id>/        → BookmarkDeleteView     (Student)
"""

import logging

from rest_framework import generics, permissions, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.mixins import SuccessResponseMixin, SoftDeleteMixin
from apps.core.permissions import (
    IsAdminLevel,
    IsStudent,
    IsStudentOrGuest,
    IsSystemAdmin,
    IsTutor,
)

from .models import (
    Course,
    Lesson,
    LessonBookmark,
    LessonQuestion,
    Module,
    QuizQuestion,
    RoadSign,
    StudentProgress,
)
from .serializers import (
    CourseDetailSerializer,
    CourseListSerializer,
    CourseStatsSerializer,
    CourseWriteSerializer,
    LessonBookmarkSerializer,
    LessonDetailSerializer,
    LessonListSerializer,
    LessonQuestionSerializer,
    LessonWriteSerializer,
    MarkLessonCompleteSerializer,
    ModuleDetailSerializer,
    ModuleListSerializer,
    ModuleWriteSerializer,
    ProgressSummarySerializer,
    QuizQuestionDetailSerializer,
    QuizQuestionListSerializer,
    QuizQuestionWriteSerializer,
    RecordQuizAttemptSerializer,
    RoadSignSerializer,
    StudentProgressSerializer,
)
from .services import ContentGateService, CourseService, ProgressService
from apps.accounts.constants import UserRole

logger = logging.getLogger("apps.lms")


# ---------------------------------------------------------------------------
# Permission helpers
# ---------------------------------------------------------------------------

def _is_content_staff(user) -> bool:
    """Tutors and above can create/edit content."""
    return user.is_authenticated and user.role in (
        UserRole.TUTOR, UserRole.SYSTEM_ADMIN
    )


def _is_admin(user) -> bool:
    return user.is_authenticated and user.role == UserRole.SYSTEM_ADMIN


# ===========================================================================
# COURSE VIEWS
# ===========================================================================

class CourseListView(SuccessResponseMixin, generics.ListAPIView):
    """
    GET /lms/courses/
    List all published courses (or all courses for tutors/admins).
    Accessible to any authenticated user.
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class   = CourseListSerializer
    filterset_fields   = ["is_published"]
    search_fields      = ["title", "description"]
    ordering_fields    = ["sort_order", "created_at", "title"]
    ordering           = ["sort_order"]

    def get_queryset(self):
        return ContentGateService.get_visible_courses(self.request.user)


class CourseCreateView(SuccessResponseMixin, generics.CreateAPIView):
    """
    POST /lms/courses/
    Tutors and Admins can create courses (draft state by default).
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class   = CourseWriteSerializer

    def get_permissions(self):
        if not _is_content_staff(self.request.user):
            self.permission_denied(
                self.request,
                message="Only tutors and administrators can create courses.",
            )
        return super().get_permissions()

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def create(self, request, *args, **kwargs):
        if not _is_content_staff(request.user):
            raise PermissionDenied("Only tutors and administrators can create courses.")
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return self.created_response(
            data=CourseDetailSerializer(serializer.instance).data,
            message="Course created as draft. Add modules and publish when ready.",
        )


class CourseDetailView(SuccessResponseMixin, generics.RetrieveAPIView):
    """
    GET /lms/courses/<id>/
    Retrieve a course with all its published modules and lessons.
    Draft courses are only visible to tutors and admins.
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class   = CourseDetailSerializer

    def get_object(self):
        try:
            course = Course.objects.get(pk=self.kwargs["pk"])
        except Course.DoesNotExist:
            raise NotFound("Course not found.")

        if not course.is_published and not _is_content_staff(self.request.user):
            raise NotFound("Course not found.")

        return course

    def retrieve(self, request, *args, **kwargs):
        course = self.get_object()
        serializer = self.get_serializer(course)
        return self.success_response(data=serializer.data)


class CourseUpdateView(SuccessResponseMixin, generics.UpdateAPIView):
    """
    PATCH /lms/courses/<id>/
    Update course metadata (tutors and admins only).
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class   = CourseWriteSerializer
    queryset           = Course.objects.all()
    http_method_names  = ["patch"]

    def get_object(self):
        if not _is_content_staff(self.request.user):
            raise PermissionDenied("Only tutors and administrators can edit courses.")
        return super().get_object()

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.updated_by = request.user
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(updated_by=request.user)
        return self.success_response(
            data=CourseDetailSerializer(serializer.instance).data,
            message="Course updated.",
        )


class CourseDeleteView(SoftDeleteMixin, SuccessResponseMixin, generics.DestroyAPIView):
    """DELETE /lms/courses/<id>/ — Admin only. Soft-deletes the course."""

    permission_classes = [permissions.IsAuthenticated]
    queryset           = Course.objects.all()

    def get_object(self):
        if not _is_admin(self.request.user):
            raise PermissionDenied("Only system administrators can delete courses.")
        return super().get_object()


class CoursePublishView(SuccessResponseMixin, APIView):
    """
    POST /lms/courses/<id>/publish/
    Admin only. Validates the course has published modules, then makes it live.
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk, *args, **kwargs):
        if not _is_admin(request.user):
            raise PermissionDenied("Only system administrators can publish courses.")

        try:
            course = Course.objects.get(pk=pk)
        except Course.DoesNotExist:
            raise NotFound("Course not found.")

        try:
            course = CourseService.publish_course(course, published_by=request.user)
        except ValueError as exc:
            raise ValidationError(str(exc))

        return self.success_response(
            data=CourseDetailSerializer(course).data,
            message=f"'{course.title}' is now published and visible to learners.",
        )


class CourseUnpublishView(SuccessResponseMixin, APIView):
    """POST /lms/courses/<id>/unpublish/ — Admin only. Moves course back to draft."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk, *args, **kwargs):
        if not _is_admin(request.user):
            raise PermissionDenied("Only system administrators can unpublish courses.")

        try:
            course = Course.objects.get(pk=pk)
        except Course.DoesNotExist:
            raise NotFound("Course not found.")

        CourseService.unpublish_course(course, unpublished_by=request.user)
        return self.success_response(
            data={"id": str(course.id), "is_published": False},
            message=f"'{course.title}' has been moved back to draft.",
        )


class CourseStatsView(SuccessResponseMixin, APIView):
    """GET /lms/courses/<id>/stats/ — Tutors and Admins only."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk, *args, **kwargs):
        if not _is_content_staff(request.user):
            raise PermissionDenied("Only tutors and administrators can view course stats.")

        try:
            course = Course.objects.get(pk=pk)
        except Course.DoesNotExist:
            raise NotFound("Course not found.")

        stats = CourseService.get_course_stats(course)
        serializer = CourseStatsSerializer(stats)
        return self.success_response(data=serializer.data)


# ===========================================================================
# MODULE VIEWS
# ===========================================================================

class ModuleListView(SuccessResponseMixin, generics.ListAPIView):
    """GET /lms/courses/<course_id>/modules/ — Modules of a course."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class   = ModuleListSerializer
    ordering           = ["sort_order"]

    def get_queryset(self):
        try:
            course = Course.objects.get(pk=self.kwargs["course_id"])
        except Course.DoesNotExist:
            raise NotFound("Course not found.")

        if not course.is_published and not _is_content_staff(self.request.user):
            raise NotFound("Course not found.")

        return ContentGateService.get_visible_modules(course, self.request.user)


class ModuleCreateView(SuccessResponseMixin, generics.CreateAPIView):
    """POST /lms/modules/ — Create a module (Tutor+Admin)."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class   = ModuleWriteSerializer

    def create(self, request, *args, **kwargs):
        if not _is_content_staff(request.user):
            raise PermissionDenied("Only tutors and administrators can create modules.")

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        module = serializer.save()
        return self.created_response(
            data=ModuleDetailSerializer(module).data,
            message="Module created as draft.",
        )


class ModuleDetailView(SuccessResponseMixin, generics.RetrieveAPIView):
    """GET /lms/modules/<id>/ — Module with its lessons."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class   = ModuleDetailSerializer

    def get_object(self):
        try:
            module = Module.objects.select_related("course").get(pk=self.kwargs["pk"])
        except Module.DoesNotExist:
            raise NotFound("Module not found.")

        if not module.is_published and not _is_content_staff(self.request.user):
            raise NotFound("Module not found.")

        return module

    def retrieve(self, request, *args, **kwargs):
        return self.success_response(data=self.get_serializer(self.get_object()).data)


class ModuleUpdateView(SuccessResponseMixin, generics.UpdateAPIView):
    """PATCH /lms/modules/<id>/ — Update module (Tutor+Admin)."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class   = ModuleWriteSerializer
    queryset           = Module.objects.all()
    http_method_names  = ["patch"]

    def update(self, request, *args, **kwargs):
        if not _is_content_staff(request.user):
            raise PermissionDenied("Only tutors and administrators can edit modules.")

        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return self.success_response(
            data=ModuleDetailSerializer(serializer.instance).data,
            message="Module updated.",
        )


class ModuleDeleteView(SoftDeleteMixin, SuccessResponseMixin, generics.DestroyAPIView):
    """DELETE /lms/modules/<id>/ — Admin only."""

    permission_classes = [permissions.IsAuthenticated]
    queryset           = Module.objects.all()

    def get_object(self):
        if not _is_admin(self.request.user):
            raise PermissionDenied("Only system administrators can delete modules.")
        return super().get_object()


class ModulePublishView(SuccessResponseMixin, APIView):
    """POST /lms/modules/<id>/publish/ — Admin only."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk, *args, **kwargs):
        if not _is_admin(request.user):
            raise PermissionDenied("Only system administrators can publish modules.")

        try:
            module = Module.objects.get(pk=pk)
        except Module.DoesNotExist:
            raise NotFound("Module not found.")

        try:
            module = CourseService.publish_module(module, published_by=request.user)
        except ValueError as exc:
            raise ValidationError(str(exc))

        return self.success_response(
            data=ModuleDetailSerializer(module).data,
            message=f"Module '{module.title}' is now published.",
        )


class ModuleUnpublishView(SuccessResponseMixin, APIView):
    """POST /lms/modules/<id>/unpublish/ — Admin only."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk, *args, **kwargs):
        if not _is_admin(request.user):
            raise PermissionDenied("Only system administrators can unpublish modules.")

        try:
            module = Module.objects.get(pk=pk)
        except Module.DoesNotExist:
            raise NotFound("Module not found.")

        module.unpublish()
        return self.success_response(
            data={"id": str(module.id), "is_published": False},
            message=f"Module '{module.title}' moved to draft.",
        )


# ===========================================================================
# LESSON VIEWS
# ===========================================================================

class LessonListView(SuccessResponseMixin, generics.ListAPIView):
    """GET /lms/modules/<module_id>/lessons/ — Lessons within a module."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class   = LessonListSerializer
    ordering           = ["sort_order"]

    def get_queryset(self):
        try:
            module = Module.objects.select_related("course").get(pk=self.kwargs["module_id"])
        except Module.DoesNotExist:
            raise NotFound("Module not found.")

        if not module.is_published and not _is_content_staff(self.request.user):
            raise NotFound("Module not found.")

        return ContentGateService.get_visible_lessons(module, self.request.user)


class LessonCreateView(SuccessResponseMixin, generics.CreateAPIView):
    """POST /lms/lessons/ — Tutor+Admin only."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class   = LessonWriteSerializer

    def create(self, request, *args, **kwargs):
        if not _is_content_staff(request.user):
            raise PermissionDenied("Only tutors and administrators can create lessons.")

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        lesson = serializer.save()
        return self.created_response(
            data=LessonDetailSerializer(lesson).data,
            message="Lesson created.",
        )


class LessonDetailView(SuccessResponseMixin, generics.RetrieveAPIView):
    """
    GET /lms/lessons/<id>/
    Retrieve a lesson. Access is checked via ContentGateService.
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class   = LessonDetailSerializer

    def get_object(self):
        try:
            lesson = Lesson.objects.select_related(
                "module__course", "road_sign"
            ).get(pk=self.kwargs["pk"])
        except Lesson.DoesNotExist:
            raise NotFound("Lesson not found.")

        if not ContentGateService.can_access_lesson(self.request.user, lesson):
            raise PermissionDenied("You do not have access to this lesson.")

        return lesson

    def retrieve(self, request, *args, **kwargs):
        return self.success_response(data=self.get_serializer(self.get_object()).data)


class LessonUpdateView(SuccessResponseMixin, generics.UpdateAPIView):
    """PATCH /lms/lessons/<id>/ — Tutor+Admin only."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class   = LessonWriteSerializer
    queryset           = Lesson.objects.all()
    http_method_names  = ["patch"]

    def update(self, request, *args, **kwargs):
        if not _is_content_staff(request.user):
            raise PermissionDenied("Only tutors and administrators can edit lessons.")

        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return self.success_response(
            data=LessonDetailSerializer(serializer.instance).data,
            message="Lesson updated.",
        )


class LessonDeleteView(SoftDeleteMixin, SuccessResponseMixin, generics.DestroyAPIView):
    """DELETE /lms/lessons/<id>/ — Admin only."""

    permission_classes = [permissions.IsAuthenticated]
    queryset           = Lesson.objects.all()

    def get_object(self):
        if not _is_admin(self.request.user):
            raise PermissionDenied("Only system administrators can delete lessons.")
        return super().get_object()


# ===========================================================================
# LESSON QUESTION VIEWS (quiz management)
# ===========================================================================

class LessonQuestionListView(SuccessResponseMixin, generics.ListAPIView):
    """GET /lms/lessons/<lesson_id>/questions/ — Questions in a quiz lesson."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class   = LessonQuestionSerializer
    ordering           = ["sort_order"]

    def get_queryset(self):
        user = self.request.user
        # Quiz questions only accessible to students and above
        if user.role not in (UserRole.STUDENT, UserRole.TUTOR, UserRole.SYSTEM_ADMIN):
            raise PermissionDenied("Quiz questions require a student or staff account.")

        return LessonQuestion.objects.filter(
            lesson_id=self.kwargs["lesson_id"],
            question__is_active=True,
        ).select_related("question__road_sign").order_by("sort_order")


class LessonQuestionAddView(SuccessResponseMixin, APIView):
    """POST /lms/lessons/<lesson_id>/questions/ — Add question to quiz (Tutor+Admin)."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, lesson_id, *args, **kwargs):
        if not _is_content_staff(request.user):
            raise PermissionDenied("Only tutors and administrators can manage quiz questions.")

        try:
            lesson = Lesson.objects.get(pk=lesson_id, lesson_type="QUIZ")
        except Lesson.DoesNotExist:
            raise NotFound("Quiz lesson not found.")

        question_id = request.data.get("question_id")
        if not question_id:
            raise ValidationError({"question_id": "This field is required."})

        try:
            question = QuizQuestion.objects.get(pk=question_id)
        except QuizQuestion.DoesNotExist:
            raise NotFound("Question not found.")

        lq, created = LessonQuestion.objects.get_or_create(
            lesson=lesson,
            question=question,
            defaults={"sort_order": lesson.lesson_questions.count() + 1},
        )
        if not created:
            raise ValidationError("This question is already in the lesson.")

        return self.created_response(
            data=LessonQuestionSerializer(lq).data,
            message="Question added to lesson.",
        )


class LessonQuestionRemoveView(SuccessResponseMixin, APIView):
    """DELETE /lms/lessons/<lesson_id>/questions/<question_id>/ — Tutor+Admin."""

    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, lesson_id, question_id, *args, **kwargs):
        if not _is_content_staff(request.user):
            raise PermissionDenied("Only tutors and administrators can remove quiz questions.")

        try:
            lq = LessonQuestion.objects.get(lesson_id=lesson_id, question_id=question_id)
        except LessonQuestion.DoesNotExist:
            raise NotFound("Question not found in this lesson.")

        lq.hard_delete()
        return self.no_content_response()


# ===========================================================================
# ROAD SIGN VIEWS
# ===========================================================================

class RoadSignListView(SuccessResponseMixin, generics.ListAPIView):
    """
    GET /lms/road-signs/
    Reference browser — all active road signs.
    Accessible to all authenticated users (guests and students).
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class   = RoadSignSerializer
    filterset_fields   = ["category", "is_active"]
    search_fields      = ["name", "sign_code", "description"]
    ordering_fields    = ["category", "name"]
    ordering           = ["category", "name"]

    def get_queryset(self):
        return RoadSign.objects.filter(is_active=True)


class RoadSignDetailView(SuccessResponseMixin, generics.RetrieveAPIView):
    """GET /lms/road-signs/<id>/ — Single road sign detail."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class   = RoadSignSerializer
    queryset           = RoadSign.objects.filter(is_active=True)


class RoadSignCreateView(SuccessResponseMixin, generics.CreateAPIView):
    """POST /lms/road-signs/ — Tutor+Admin only."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class   = RoadSignSerializer

    def create(self, request, *args, **kwargs):
        if not _is_content_staff(request.user):
            raise PermissionDenied("Only tutors and administrators can add road signs.")

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return self.created_response(data=serializer.data, message="Road sign added.")


class RoadSignUpdateView(SuccessResponseMixin, generics.UpdateAPIView):
    """PATCH /lms/road-signs/<id>/ — Admin only."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class   = RoadSignSerializer
    queryset           = RoadSign.objects.all()
    http_method_names  = ["patch"]

    def update(self, request, *args, **kwargs):
        if not _is_admin(request.user):
            raise PermissionDenied("Only system administrators can edit road signs.")

        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return self.success_response(data=serializer.data, message="Road sign updated.")


# ===========================================================================
# QUIZ QUESTION VIEWS
# ===========================================================================

class QuizQuestionListView(SuccessResponseMixin, generics.ListAPIView):
    """
    GET /lms/questions/
    Question bank browser — Students, Tutors, Admins only.
    Correct answers are NOT exposed in this list view.
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class   = QuizQuestionListSerializer
    filterset_fields   = ["domain", "difficulty", "is_active"]
    search_fields      = ["question_text", "question_text_kinyarwanda"]
    ordering_fields    = ["domain", "difficulty", "created_at"]
    ordering           = ["domain", "difficulty"]

    def get_queryset(self):
        if self.request.user.role not in (
            UserRole.STUDENT, UserRole.TUTOR, UserRole.SYSTEM_ADMIN
        ):
            raise PermissionDenied("Quiz questions are only accessible to students and staff.")
        return QuizQuestion.objects.filter(is_active=True)


class QuizQuestionDetailView(SuccessResponseMixin, generics.RetrieveAPIView):
    """
    GET /lms/questions/<id>/
    Full question detail including correct answer.
    Correct answer revealed only for tutors/admins OR after a quiz is submitted.
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class   = QuizQuestionDetailSerializer
    queryset           = QuizQuestion.objects.all()

    def get_object(self):
        if self.request.user.role not in (
            UserRole.STUDENT, UserRole.TUTOR, UserRole.SYSTEM_ADMIN
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
# STUDENT PROGRESS VIEWS
# ===========================================================================

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
    """
    POST /lms/progress/complete/
    Mark a lesson as completed. Student role required.
    """

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
    """
    POST /lms/progress/quiz/
    Record a quiz attempt result. Student role required.
    """

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


# ===========================================================================
# BOOKMARK VIEWS
# ===========================================================================

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
        serializer = self.get_serializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)

        # Verify lesson access before bookmarking
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
