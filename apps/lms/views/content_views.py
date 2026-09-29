"""
apps/lms/views/content_views.py
=================================
Module, Lesson, LessonQuestion, and RoadSign API views.

Endpoints:
  GET       /lms/courses/<id>/modules/          → ModuleListView
  POST      /lms/modules/                        → ModuleCreateView
  GET/PATCH /lms/modules/<id>/                   → ModuleDetailView, ModuleUpdateView
  DELETE    /lms/modules/<id>/                   → ModuleDeleteView
  POST      /lms/modules/<id>/publish/           → ModulePublishView
  POST      /lms/modules/<id>/unpublish/         → ModuleUnpublishView
  GET       /lms/modules/<id>/lessons/           → LessonListView
  POST      /lms/lessons/                        → LessonCreateView
  GET/PATCH /lms/lessons/<id>/                   → LessonDetailView, LessonUpdateView
  DELETE    /lms/lessons/<id>/                   → LessonDeleteView
  GET       /lms/lessons/<id>/questions/         → LessonQuestionListView
  POST      /lms/lessons/<id>/questions/         → LessonQuestionAddView
  DELETE    /lms/lessons/<id>/questions/<qid>/   → LessonQuestionRemoveView
  GET/POST  /lms/road-signs/                     → RoadSignListView, RoadSignCreateView
  GET       /lms/road-signs/<id>/                → RoadSignDetailView
  PATCH     /lms/road-signs/<id>/                → RoadSignUpdateView
"""

from rest_framework import generics, permissions
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.views import APIView

from apps.core.mixins import SuccessResponseMixin, SoftDeleteMixin
from apps.accounts.constants import UserRole
from apps.lms.models import (
    Course, Lesson, LessonBookmark, LessonQuestion, Module, QuizQuestion, RoadSign
)
from apps.lms.serializers import (
    LessonDetailSerializer,
    LessonListSerializer,
    LessonQuestionSerializer,
    LessonWriteSerializer,
    ModuleDetailSerializer,
    ModuleListSerializer,
    ModuleWriteSerializer,
    RoadSignSerializer,
)
from apps.lms.services import ContentGateService, CourseService


def _is_content_staff(user) -> bool:
    return user.is_authenticated and user.role in (
        UserRole.TUTOR, UserRole.TRAINING_ADMIN, UserRole.SYSTEM_ADMIN
    )


def _is_admin(user) -> bool:
    return user.is_authenticated and user.role in (
        UserRole.TRAINING_ADMIN, UserRole.SYSTEM_ADMIN
    )


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
    """GET /lms/lessons/<id>/ — Retrieve a lesson with access gate."""
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
        if user.role not in (
            UserRole.STUDENT, UserRole.TUTOR, UserRole.TRAINING_ADMIN, UserRole.SYSTEM_ADMIN
        ):
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
    """GET /lms/road-signs/ — Reference browser for all active road signs."""
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
