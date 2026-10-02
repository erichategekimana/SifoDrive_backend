"""
apps/lms/views/curriculum_views.py
====================================
Curriculum and Course API views.

Endpoints:
  GET/POST  /lms/curricula/              → CurriculumListView, CurriculumCreateView
  GET/PATCH /lms/curricula/<id>/         → CurriculumDetailView, CurriculumUpdateView
  DELETE    /lms/curricula/<id>/delete/  → CurriculumDeleteView
  POST      /lms/curricula/<id>/publish/ → CurriculumPublishView
  POST      /lms/curricula/<id>/unpublish/ → CurriculumUnpublishView
  GET       /lms/curricula/<id>/courses/ → CurriculumCoursesListView
  GET/POST  /lms/courses/               → CourseListView, CourseCreateView
  GET       /lms/courses/<id>/          → CourseDetailView
  PATCH     /lms/courses/<id>/          → CourseUpdateView
  DELETE    /lms/courses/<id>/          → CourseDeleteView
  POST      /lms/courses/<id>/publish/  → CoursePublishView
  POST      /lms/courses/<id>/unpublish/ → CourseUnpublishView
  GET       /lms/courses/<id>/stats/    → CourseStatsView
"""

from rest_framework import generics, permissions, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.views import APIView

from apps.core.mixins import SuccessResponseMixin, SoftDeleteMixin
from apps.accounts.constants import UserRole
from apps.lms.models import Course, Curriculum
from apps.lms.serializers import (
    CourseDetailSerializer,
    CourseListSerializer,
    CourseStatsSerializer,
    CourseWriteSerializer,
    CurriculumDetailSerializer,
    CurriculumListSerializer,
    CurriculumWriteSerializer,
)
from apps.lms.services import ContentGateService, CourseService


def _is_content_staff(user) -> bool:
    """Tutors, Training Admins, and System Admins can view/manage learning materials."""
    return user.is_authenticated and user.role in (
        UserRole.TUTOR, UserRole.TRAINING_ADMIN, UserRole.SYSTEM_ADMIN
    )


def _is_system_admin(user) -> bool:
    """System Admins only (and superusers) have control over Curricula and Courses."""
    return user.is_authenticated and (
        user.is_superuser or user.role == UserRole.SYSTEM_ADMIN
    )


# ===========================================================================
# CURRICULUM VIEWS
# ===========================================================================

class CurriculumListView(SuccessResponseMixin, generics.ListAPIView):
    """GET /lms/curricula/ — List all curricula (published for learners, all for staff)."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = CurriculumListSerializer
    search_fields = ["title", "title_kinyarwanda", "code", "description"]
    ordering_fields = ["sort_order", "created_at", "title"]
    ordering = ["sort_order", "-created_at"]

    def get_queryset(self):
        user = self.request.user
        qs = Curriculum.objects.filter(is_deleted=False)
        if not (user.is_authenticated and user.role in (
            UserRole.SYSTEM_ADMIN, UserRole.TRAINING_ADMIN, UserRole.TUTOR
        )):
            qs = qs.filter(is_published=True)
        return qs


class CurriculumCreateView(SuccessResponseMixin, generics.CreateAPIView):
    """POST /lms/curricula/create/ — System Admin only."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = CurriculumWriteSerializer

    def create(self, request, *args, **kwargs):
        if not _is_system_admin(request.user):
            raise PermissionDenied("Only System Administrators can create curricula.")
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save(created_by=request.user)
        return self.created_response(
            data=CurriculumDetailSerializer(instance).data,
            message="Curriculum created successfully.",
        )


class CurriculumDetailView(SuccessResponseMixin, generics.RetrieveAPIView):
    """GET /lms/curricula/<id>/ — Retrieve a curriculum with its nested courses."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = CurriculumDetailSerializer

    def get_object(self):
        try:
            curr = Curriculum.objects.get(pk=self.kwargs["pk"], is_deleted=False)
        except Curriculum.DoesNotExist:
            raise NotFound("Curriculum not found.")
        user = self.request.user
        if not curr.is_published and not (
            user.is_authenticated and user.role in (
                UserRole.SYSTEM_ADMIN, UserRole.TRAINING_ADMIN, UserRole.TUTOR
            )
        ):
            raise NotFound("Curriculum not found.")
        return curr


class CurriculumUpdateView(SuccessResponseMixin, generics.UpdateAPIView):
    """PATCH /lms/curricula/<id>/edit/ — System Admin only."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = CurriculumWriteSerializer

    def get_object(self):
        try:
            return Curriculum.objects.get(pk=self.kwargs["pk"], is_deleted=False)
        except Curriculum.DoesNotExist:
            raise NotFound("Curriculum not found.")

    def update(self, request, *args, **kwargs):
        if not _is_system_admin(request.user):
            raise PermissionDenied("Only System Administrators can edit curricula.")
        partial = kwargs.pop('partial', True)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save(updated_by=request.user)
        return self.success_response(
            data=CurriculumDetailSerializer(instance).data,
            message="Curriculum updated successfully.",
        )


class CurriculumDeleteView(SuccessResponseMixin, APIView):
    """DELETE /lms/curricula/<id>/delete/ — System Admin only (soft-delete)."""
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, pk, *args, **kwargs):
        if not _is_system_admin(request.user):
            raise PermissionDenied("Only System Administrators can delete curricula.")
        try:
            curr = Curriculum.objects.get(pk=pk, is_deleted=False)
        except Curriculum.DoesNotExist:
            raise NotFound("Curriculum not found.")
        curr.soft_delete(deleted_by=request.user)
        return self.success_response(message=f"Curriculum '{curr.title}' deleted successfully.")


class CurriculumPublishView(SuccessResponseMixin, APIView):
    """POST /lms/curricula/<id>/publish/ — System Admin only."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk, *args, **kwargs):
        if not _is_system_admin(request.user):
            raise PermissionDenied("Only System Administrators can publish curricula.")
        try:
            curr = Curriculum.objects.get(pk=pk, is_deleted=False)
        except Curriculum.DoesNotExist:
            raise NotFound("Curriculum not found.")
        curr.publish(published_by=request.user)
        return self.success_response(
            data=CurriculumDetailSerializer(curr).data,
            message=f"Curriculum '{curr.title}' is now published.",
        )


class CurriculumUnpublishView(SuccessResponseMixin, APIView):
    """POST /lms/curricula/<id>/unpublish/ — System Admin only."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk, *args, **kwargs):
        if not _is_system_admin(request.user):
            raise PermissionDenied("Only System Administrators can unpublish curricula.")
        try:
            curr = Curriculum.objects.get(pk=pk, is_deleted=False)
        except Curriculum.DoesNotExist:
            raise NotFound("Curriculum not found.")
        curr.unpublish()
        return self.success_response(
            data=CurriculumDetailSerializer(curr).data,
            message=f"Curriculum '{curr.title}' moved to draft. All child courses have been moved to draft.",
        )


class CurriculumCoursesListView(SuccessResponseMixin, generics.ListAPIView):
    """GET /lms/curricula/<id>/courses/ — List courses under a specific curriculum."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = CourseListSerializer

    def get_queryset(self):
        curr_id = self.kwargs["pk"]
        user = self.request.user
        qs = Course.objects.filter(curriculum_id=curr_id, is_deleted=False)
        if not (user.is_authenticated and user.role in (
            UserRole.SYSTEM_ADMIN, UserRole.TRAINING_ADMIN, UserRole.TUTOR
        )):
            curr = Curriculum.objects.filter(id=curr_id, is_deleted=False).first()
            if not curr or not curr.is_published:
                return Course.objects.none()
            qs = qs.filter(is_published=True)
        return qs.order_by("sort_order", "created_at")


# ===========================================================================
# COURSE VIEWS
# ===========================================================================

class CourseListView(SuccessResponseMixin, generics.ListAPIView):
    """GET /lms/courses/ — List all published courses (or all courses for tutors/admins)."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class   = CourseListSerializer
    filterset_fields   = ["is_published", "curriculum"]
    search_fields      = ["title", "description", "code"]
    ordering_fields    = ["sort_order", "created_at", "title"]
    ordering           = ["sort_order"]

    def get_queryset(self):
        return ContentGateService.get_visible_courses(self.request.user)


class CourseCreateView(SuccessResponseMixin, generics.CreateAPIView):
    """POST /lms/courses/ — System Admin only."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class   = CourseWriteSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def create(self, request, *args, **kwargs):
        if not _is_system_admin(request.user):
            raise PermissionDenied("Only System Administrators can create curriculum courses.")
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return self.created_response(
            data=CourseDetailSerializer(serializer.instance).data,
            message="Curriculum course created as draft.",
        )


class CourseDetailView(SuccessResponseMixin, generics.RetrieveAPIView):
    """GET /lms/courses/<id>/ — Retrieve a course with all its published modules and lessons."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class   = CourseDetailSerializer

    def get_object(self):
        try:
            course = Course.objects.get(pk=self.kwargs["pk"], is_deleted=False)
        except Course.DoesNotExist:
            raise NotFound("Course not found.")
        if not _is_content_staff(self.request.user):
            if not course.is_published:
                raise NotFound("Course not found.")
            if course.curriculum and not course.curriculum.is_published:
                raise NotFound("Course not found.")
        return course

    def retrieve(self, request, *args, **kwargs):
        return self.success_response(data=self.get_serializer(self.get_object()).data)


class CourseUpdateView(SuccessResponseMixin, generics.UpdateAPIView):
    """PATCH /lms/courses/<id>/ — System Admin only."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class   = CourseWriteSerializer
    queryset           = Course.objects.all()
    http_method_names  = ["patch"]

    def get_object(self):
        if not _is_system_admin(self.request.user):
            raise PermissionDenied("Only System Administrators can edit curriculum courses.")
        return super().get_object()

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(updated_by=request.user)
        return self.success_response(
            data=CourseDetailSerializer(serializer.instance).data,
            message="Course updated.",
        )


class CourseDeleteView(SoftDeleteMixin, SuccessResponseMixin, generics.DestroyAPIView):
    """DELETE /lms/courses/<id>/ — System Admin only. Soft-deletes the course."""
    permission_classes = [permissions.IsAuthenticated]
    queryset           = Course.objects.all()

    def get_object(self):
        if not _is_system_admin(self.request.user):
            raise PermissionDenied("Only System Administrators can delete curriculum courses.")
        return super().get_object()


class CoursePublishView(SuccessResponseMixin, APIView):
    """POST /lms/courses/<id>/publish/ — System Admin only."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk, *args, **kwargs):
        if not _is_system_admin(request.user):
            raise PermissionDenied("Only System Administrators can publish courses.")
        try:
            course = Course.objects.get(pk=pk, is_deleted=False)
        except Course.DoesNotExist:
            raise NotFound("Course not found.")
        try:
            course = CourseService.publish_course(course, published_by=request.user)
        except (ValueError, ValidationError) as exc:
            raise ValidationError(str(exc))
        return self.success_response(
            data=CourseDetailSerializer(course).data,
            message=f"'{course.title}' is now published and visible to learners.",
        )


class CourseUnpublishView(SuccessResponseMixin, APIView):
    """POST /lms/courses/<id>/unpublish/ — System Admin only."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk, *args, **kwargs):
        if not _is_system_admin(request.user):
            raise PermissionDenied("Only System Administrators can unpublish courses.")
        try:
            course = Course.objects.get(pk=pk, is_deleted=False)
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
        return self.success_response(data=CourseStatsSerializer(stats).data)
