"""
apps/accounts/views/admin_views.py
=====================================
Admin user management views (System Admin & Training Admin).

Endpoints:
  GET  /auth/users/                      → UserListView
  POST /auth/users/create/               → AdminUserCreateView
  GET  /auth/users/<user_id>/            → AdminUserDetailView
  POST /auth/users/<user_id>/role/       → AdminUserRoleUpdateView
  POST /auth/users/<user_id>/status/     → AdminUserStatusUpdateView
  POST /auth/users/<user_id>/tutor/      → AdminUserTutorAssignView
  GET  /auth/admin/stats/                → AdminDashboardStatsView
"""

import logging

from django.contrib.auth import get_user_model
from rest_framework import generics, permissions, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.views import APIView

from apps.accounts.constants import AccountStatus, UserRole
from apps.core.mixins import SuccessResponseMixin
from apps.core.permissions import IsSystemAdmin, IsTrainingAdminOrAbove

from apps.accounts.serializers import (
    AdminCreateUserSerializer,
    AdminUserDetailSerializer,
    AdminUserListSerializer,
    AdminUserRoleUpdateSerializer,
    AdminUserStatusUpdateSerializer,
)
from apps.accounts.services import UserService

User = get_user_model()
logger = logging.getLogger(__name__)


class UserListView(SuccessResponseMixin, generics.ListAPIView):
    """
    GET /api/v1/auth/users/
    System Admin & Training Admin — paginated list of users.
    Supports filtering by role / status and searching by phone / name / student_id.
    """
    permission_classes = [IsTrainingAdminOrAbove]
    serializer_class = AdminUserListSerializer
    filterset_fields = ["role", "status"]
    search_fields = ["phone_number", "first_name", "last_name", "email", "student_id"]
    ordering_fields = ["created_at", "last_name", "role", "status"]
    ordering = ["-created_at"]

    def get_queryset(self):
        qs = User.objects.all().select_related("assigned_tutor").prefetch_related("enrolled_cohorts")
        if self.request.user.role == UserRole.TRAINING_ADMIN:
            qs = qs.exclude(role=UserRole.SYSTEM_ADMIN)
        return qs


class AdminDashboardStatsView(SuccessResponseMixin, APIView):
    """
    GET /api/v1/auth/admin/stats/
    Command Center platform metrics for System Admin & Training Admin.
    """
    permission_classes = [IsTrainingAdminOrAbove]

    def get(self, request, *args, **kwargs):
        from apps.accounts.models import User
        from apps.booking.models import BookingApplication, BookingState
        from apps.examinations.models import ExamSession
        from apps.lms.models import Course

        total_registered_users = User.objects.count()
        enrolled_students = User.objects.filter(role=UserRole.STUDENT).count()
        total_booking_orders = BookingApplication.objects.count()
        lms_courses = Course.objects.filter(is_deleted=False).count()

        graduated_from_exams = ExamSession.objects.filter(passed=True).values("student").distinct().count()
        completed_bookings = BookingApplication.objects.filter(
            state=BookingState.COMPLETED
        ).values("applicant").distinct().count()
        total_graduated_students = max(graduated_from_exams, completed_bookings)

        return self.success_response(data={
            "total_registered_users": total_registered_users,
            "total_booking_orders": total_booking_orders,
            "enrolled_students": enrolled_students,
            "total_graduated_students": total_graduated_students,
            "lms_courses": lms_courses,
        })


class AdminUserCreateView(SuccessResponseMixin, generics.CreateAPIView):
    """
    POST /api/v1/auth/users/create/
    System Admin & Training Admin: Creates accounts for other roles.
    STRICT PRIVILEGE BOUNDARY: Cannot create another SYSTEM_ADMIN.
    """
    permission_classes = [IsTrainingAdminOrAbove]
    serializer_class = AdminCreateUserSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return self.success_response(
            data=AdminUserDetailSerializer(user).data,
            message=f"Account created successfully for {user.full_name} ({user.role}).",
            status_code=status.HTTP_201_CREATED,
        )


class AdminUserDetailView(SuccessResponseMixin, generics.RetrieveAPIView):
    """GET /api/v1/auth/users/<uuid:user_id>/ — Inspect full user profile."""
    permission_classes = [IsTrainingAdminOrAbove]
    serializer_class = AdminUserDetailSerializer
    lookup_field = "id"
    lookup_url_kwarg = "user_id"

    def get_queryset(self):
        qs = User.objects.all().select_related("assigned_tutor")
        if self.request.user.role == UserRole.TRAINING_ADMIN:
            qs = qs.exclude(role=UserRole.SYSTEM_ADMIN)
        return qs

    def retrieve(self, request, *args, **kwargs):
        return self.success_response(data=self.get_serializer(self.get_object()).data)


class AdminUserRoleUpdateView(SuccessResponseMixin, APIView):
    """
    POST /api/v1/auth/users/<uuid:user_id>/role/
    System Admin & Training Admin — updates user's role.
    STRICT PRIVILEGE BOUNDARY: Cannot promote to SYSTEM_ADMIN.
    """
    permission_classes = [IsTrainingAdminOrAbove]

    def post(self, request, user_id, *args, **kwargs):
        try:
            target_user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            raise NotFound("User not found.")

        if target_user.role == UserRole.SYSTEM_ADMIN:
            raise ValidationError("Role of SYSTEM_ADMIN accounts cannot be modified via portal.")

        serializer = AdminUserRoleUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_role = serializer.validated_data["role"]

        if request.user.role == UserRole.TRAINING_ADMIN:
            if (
                target_user.role not in [UserRole.STUDENT, UserRole.GUEST]
                or new_role not in [UserRole.STUDENT, UserRole.GUEST]
            ):
                raise ValidationError(
                    "Training administrators may only modify roles between Student and Guest."
                )

        user = UserService.promote_to_role(
            user=target_user, new_role=new_role, promoted_by=request.user
        )
        return self.success_response(
            data=AdminUserDetailSerializer(user).data,
            message=f"User role updated to {user.role}.",
        )


class AdminUserStatusUpdateView(SuccessResponseMixin, APIView):
    """
    POST /api/v1/auth/users/<uuid:user_id>/status/
    System Admin & Training Admin — activate, deactivate, suspend, or blacklist user.
    """
    permission_classes = [IsTrainingAdminOrAbove]

    def post(self, request, user_id, *args, **kwargs):
        try:
            target_user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            raise NotFound("User not found.")

        if target_user.role == UserRole.SYSTEM_ADMIN and target_user != request.user:
            raise ValidationError("Status of other SYSTEM_ADMIN accounts cannot be altered.")

        if request.user.role == UserRole.TRAINING_ADMIN:
            if target_user.role not in [UserRole.STUDENT, UserRole.GUEST, UserRole.TUTOR]:
                raise ValidationError(
                    "Training administrators can only modify the status of students, guests, or tutors."
                )

        serializer = AdminUserStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_status = serializer.validated_data["status"]
        reason = serializer.validated_data.get("reason", "")

        status_actions = {
            AccountStatus.ACTIVE: target_user.activate,
            AccountStatus.DEACTIVATED: target_user.deactivate,
            AccountStatus.SUSPENDED: target_user.suspend,
            AccountStatus.BLACKLISTED: target_user.blacklist,
        }
        action = status_actions.get(new_status)
        if action:
            action()

        logger.info(
            "User status changed | target=%s status=%s reason=%s by=%s",
            str(target_user.id)[:8], new_status, reason, str(request.user.id)[:8],
        )

        return self.success_response(
            data=AdminUserDetailSerializer(target_user).data,
            message=f"User account status changed to {target_user.status}.",
        )


class AdminUserTutorAssignView(SuccessResponseMixin, APIView):
    """
    POST /api/v1/auth/users/<uuid:user_id>/tutor/
    Assign or unassign an individual tutor for a student.
    """
    permission_classes = [IsTrainingAdminOrAbove]

    def post(self, request, user_id, *args, **kwargs):
        try:
            target_user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            raise NotFound("Student not found.")

        if target_user.role not in [UserRole.STUDENT, UserRole.GUEST]:
            raise ValidationError("Tutors can only be assigned to students or guests.")

        tutor_id = request.data.get("tutor_id")
        if tutor_id:
            try:
                tutor = User.objects.get(id=tutor_id, role=UserRole.TUTOR)
            except User.DoesNotExist:
                raise ValidationError("Selected tutor was not found or is not a registered tutor.")
            target_user.assigned_tutor = tutor
            message = f"Assigned tutor {tutor.full_name or tutor.phone_number} to {target_user.full_name or target_user.phone_number}."
        else:
            target_user.assigned_tutor = None
            message = f"Removed assigned tutor from {target_user.full_name or target_user.phone_number}."

        target_user.save(update_fields=["assigned_tutor", "updated_at"])
        return self.success_response(data=AdminUserListSerializer(target_user).data, message=message)
