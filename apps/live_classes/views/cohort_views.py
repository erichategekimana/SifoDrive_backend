import logging

from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from django.core.exceptions import ValidationError as DjangoValidationError

from apps.accounts.constants import UserRole
from apps.core.mixins import SuccessResponseMixin
from apps.core.permissions import (
    IsStudentOrStaff,
    IsTrainingAdminOrAbove,
)
from apps.live_classes.models import Cohort
from apps.live_classes.models.cohort import CohortStatus
from apps.live_classes.serializers import (
    CohortAssignStudentsSerializer,
    CohortAssignTutorsSerializer,
    CohortCreateUpdateSerializer,
    CohortDetailSerializer,
    CohortListSerializer,
    CohortSetStatusSerializer,
)
from apps.live_classes.services import CohortService

logger = logging.getLogger("apps.live_classes.views")


class CohortListCreateView(SuccessResponseMixin, generics.ListCreateAPIView):
    """
    GET: List active cohorts (Staff sees all; students see their enrolled cohorts).
    POST: Create a new cohort (System Admin & Training Admin only).
    """

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsTrainingAdminOrAbove()]
        return [IsStudentOrStaff()]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return CohortCreateUpdateSerializer
        return CohortListSerializer

    def get_queryset(self):
        CohortService.evaluate_all_cohorts_status()
        user = self.request.user
        if user.role in [UserRole.SYSTEM_ADMIN, UserRole.TRAINING_ADMIN, UserRole.TUTOR, UserRole.BOARD_REVIEWER]:
            return Cohort.objects.all().prefetch_related("assigned_tutors", "students")
        return user.enrolled_cohorts.filter(is_active=True)

    def perform_create(self, serializer):
        data = serializer.validated_data
        cohort = CohortService.create_cohort(
            name=data["name"],
            start_date=data["start_date"],
            code=data.get("code"),
            end_date=data.get("end_date"),
            max_capacity=data.get("max_capacity", 60),
            schedule_description=data.get("schedule_description", ""),
            description=data.get("description", ""),
            status=data.get("status", CohortStatus.QUEUE),
        )
        serializer.instance = cohort


class CohortDetailView(SuccessResponseMixin, generics.RetrieveUpdateDestroyAPIView):
    """
    GET: View detailed cohort information with tutor assignments and roster size.
    PATCH/PUT: Update cohort details (Admin & Training Admin).
    DELETE: Soft-delete / deactivate cohort (Admin & Training Admin).
    """

    queryset = Cohort.objects.all().prefetch_related("assigned_tutors", "students")

    def get_permissions(self):
        if self.request.method in ["PATCH", "PUT", "DELETE"]:
            return [IsTrainingAdminOrAbove()]
        return [IsStudentOrStaff()]

    def get_serializer_class(self):
        if self.request.method in ["PATCH", "PUT"]:
            return CohortCreateUpdateSerializer
        return CohortDetailSerializer

    def get_object(self):
        obj = super().get_object()
        obj.evaluate_status(save=True)
        return obj

    def perform_update(self, serializer):
        new_status = serializer.validated_data.pop("status", None)
        instance = serializer.save()
        if new_status:
            try:
                CohortService.set_cohort_status(instance, new_status)
            except DjangoValidationError as e:
                raise ValidationError({"status": list(e.messages) if hasattr(e, "messages") else str(e)})

    def perform_destroy(self, instance):
        can_deactivate, ongoing = CohortService.can_deactivate_cohort(instance)
        if not can_deactivate:
            raise ValidationError(
                f"Cannot deactivate cohort '{instance.name}'. There are {ongoing} active student(s) currently enrolled who have not completed or withdrawn from the course."
            )
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])


class CohortSetStatusView(SuccessResponseMixin, APIView):
    """
    POST: Set status for a cohort ('queue', 'open', 'closed', 'ended').
    Setting 'open' makes this cohort the default for new students, and automatically
    transitions any previously open cohort to 'closed'.
    """

    permission_classes = [IsTrainingAdminOrAbove]

    def post(self, request, pk):
        try:
            cohort = Cohort.objects.get(pk=pk)
        except Cohort.DoesNotExist:
            return Response({"detail": "Cohort not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = CohortSetStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        target_status = serializer.validated_data["status"]

        try:
            cohort = CohortService.set_cohort_status(cohort, target_status)
        except DjangoValidationError as e:
            raise ValidationError({"status": list(e.messages) if hasattr(e, "messages") else str(e)})

        return self.success_response(
            data={
                "id": str(cohort.id),
                "name": cohort.name,
                "code": cohort.code,
                "status": cohort.status,
                "is_active": cohort.is_active,
                "student_count": cohort.students.count(),
                "max_capacity": cohort.max_capacity,
            },
            message=f"Cohort '{cohort.name}' status successfully changed to '{cohort.status}'.",
        )


class CohortAssignStudentsView(SuccessResponseMixin, APIView):
    """
    POST: Enroll or unenroll students in a cohort (Training Admin & System Admin).
    Action can be 'enroll' (default) or 'unenroll'.
    """

    permission_classes = [IsTrainingAdminOrAbove]

    def post(self, request, pk):
        try:
            cohort = Cohort.objects.get(pk=pk)
        except Cohort.DoesNotExist:
            return Response({"detail": "Cohort not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = CohortAssignStudentsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        action = request.query_params.get("action", "enroll").lower()
        student_ids = serializer.validated_data["student_ids"]

        if action == "unenroll":
            count = CohortService.unenroll_students(cohort, student_ids)
            return self.success_response(
                data={
                    "cohort_id": str(cohort.id),
                    "students_count": cohort.students.count(),
                    "removed_count": count,
                },
                message=f"Successfully removed {count} students from cohort {cohort.code}.",
            )

        count, warnings = CohortService.enroll_students(cohort, student_ids)
        resp_data = {
            "cohort_id": str(cohort.id),
            "students_count": cohort.students.count(),
            "enrolled_count": count,
        }
        if warnings:
            resp_data["warnings"] = warnings
        return self.success_response(
            data=resp_data,
            message=f"Successfully enrolled {count} students into cohort {cohort.code}.",
        )


class CohortAssignTutorsView(SuccessResponseMixin, APIView):
    """
    POST: Assign or unassign tutors to a cohort (Training Admin & System Admin).
    Action can be 'assign' (default) or 'unassign'.
    """

    permission_classes = [IsTrainingAdminOrAbove]

    def post(self, request, pk):
        try:
            cohort = Cohort.objects.get(pk=pk)
        except Cohort.DoesNotExist:
            return Response({"detail": "Cohort not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = CohortAssignTutorsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        action = request.query_params.get("action", "assign").lower()
        tutor_ids = serializer.validated_data["tutor_ids"]

        if action == "unassign":
            count = CohortService.unassign_tutors(cohort, tutor_ids)
            return self.success_response(
                data={
                    "cohort_id": str(cohort.id),
                    "tutors_count": cohort.assigned_tutors.count(),
                    "unassigned_count": count,
                },
                message=f"Successfully unassigned {count} tutors from cohort {cohort.code}.",
            )

        count = CohortService.assign_tutors(cohort, tutor_ids)
        return self.success_response(
            data={
                "cohort_id": str(cohort.id),
                "tutors_count": cohort.assigned_tutors.count(),
                "assigned_count": count,
            },
            message=f"Successfully assigned {count} tutors to cohort {cohort.code}.",
        )
