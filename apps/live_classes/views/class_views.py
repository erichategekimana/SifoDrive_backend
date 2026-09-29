from datetime import date
import logging

from django.db.models import Q
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.constants import UserRole
from apps.core.mixins import SuccessResponseMixin
from apps.core.permissions import (
    IsStudentOrStaff,
    IsTrainingAdminOrAbove,
    IsTutorOrTrainingAdmin,
)
from apps.live_classes.models import LiveClass
from apps.live_classes.serializers import (
    LiveClassCreateUpdateSerializer,
    LiveClassDetailSerializer,
    LiveClassEndSessionSerializer,
    LiveClassListSerializer,
    LiveClassRecurringScheduleSerializer,
    LiveClassRescheduleSerializer,
)
from apps.live_classes.services import LiveClassService

logger = logging.getLogger("apps.live_classes.views")


class LiveClassListCreateView(SuccessResponseMixin, generics.ListCreateAPIView):
    """
    GET: List live tutoring sessions filtered by user role, cohort, and date.
    POST: Schedule a new live class session with Google Meet URL (Admin & Training Admin).
    """

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsTrainingAdminOrAbove()]
        return [IsStudentOrStaff()]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return LiveClassCreateUpdateSerializer
        return LiveClassListSerializer

    def get_queryset(self):
        user = self.request.user
        qs = LiveClass.objects.select_related("cohort", "tutor", "module", "lesson").all()

        # Role filtering
        if user.role == UserRole.STUDENT:
            student_cohort_ids = list(user.enrolled_cohorts.filter(is_active=True).values_list("id", flat=True))
            qs = qs.filter(
                Q(cohort_id__in=student_cohort_ids) | Q(cohort__isnull=True),
                is_published=True,
            )
        elif user.role == UserRole.TUTOR:
            tutor_cohort_ids = list(user.assigned_cohorts.filter(is_active=True).values_list("id", flat=True))
            qs = qs.filter(
                Q(tutor=user) | Q(cohort_id__in=tutor_cohort_ids) | Q(cohort__isnull=True)
            )

        # Query param filters
        status_param = self.request.query_params.get("status")
        if status_param:
            qs = qs.filter(status=status_param.upper())

        cohort_param = self.request.query_params.get("cohort")
        if cohort_param:
            qs = qs.filter(cohort_id=cohort_param)

        date_param = self.request.query_params.get("date")
        if date_param:
            qs = qs.filter(scheduled_date=date_param)

        is_past_param = self.request.query_params.get("upcoming")
        if is_past_param and is_past_param.lower() in ["true", "1"]:
            qs = qs.filter(scheduled_date__gte=date.today())

        return qs.order_by("scheduled_date", "start_time")

    def perform_create(self, serializer):
        data = serializer.validated_data
        live_class = LiveClassService.schedule_class(
            title=data["title"],
            scheduled_date=data["scheduled_date"],
            start_time=data["start_time"],
            end_time=data["end_time"],
            google_meet_url=data["google_meet_url"],
            topic=data.get("topic", ""),
            cohort=data.get("cohort"),
            tutor=data.get("tutor"),
            module=data.get("module"),
            lesson=data.get("lesson"),
            notes=data.get("notes", ""),
            is_published=data.get("is_published", True),
            created_by=self.request.user,
        )
        serializer.instance = live_class


class LiveClassRecurringScheduleView(SuccessResponseMixin, APIView):
    """
    POST: Schedule recurring live classes across a period (e.g. each Tuesday 2pm for 3 months).
    Restricted to Training Admin & System Admin.
    """

    permission_classes = [IsTrainingAdminOrAbove]

    def post(self, request, *args, **kwargs):
        serializer = LiveClassRecurringScheduleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        created_classes = LiveClassService.schedule_recurring_classes(
            **serializer.validated_data,
            created_by=request.user,
        )
        return self.success_response(
            data=LiveClassListSerializer(created_classes, many=True).data,
            message=f"Successfully scheduled {len(created_classes)} recurring live classes.",
        )


class LiveClassDetailView(SuccessResponseMixin, generics.RetrieveUpdateDestroyAPIView):
    """
    GET: View full session details, resources, and Google Meet URL.
    PATCH/PUT: Update class information (Training Admin & System Admin).
    DELETE: Soft-delete/cancel class session (Training Admin & System Admin).
    """

    queryset = LiveClass.objects.select_related(
        "cohort", "tutor", "module", "lesson", "created_by"
    ).prefetch_related("resources")

    def get_permissions(self):
        if self.request.method in ["PATCH", "PUT", "DELETE"]:
            return [IsTrainingAdminOrAbove()]
        return [IsStudentOrStaff()]

    def get_serializer_class(self):
        if self.request.method in ["PATCH", "PUT"]:
            return LiveClassCreateUpdateSerializer
        return LiveClassDetailSerializer

    def perform_destroy(self, instance):
        LiveClassService.cancel_class(instance, reason="Cancelled via admin dashboard")


class LiveClassRescheduleView(SuccessResponseMixin, APIView):
    """
    POST: Reschedule a session date/time and alert enrolled students (Training Admin & System Admin).
    """

    permission_classes = [IsTrainingAdminOrAbove]

    def post(self, request, pk):
        try:
            live_class = LiveClass.objects.get(pk=pk)
        except LiveClass.DoesNotExist:
            return Response({"detail": "Live class not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = LiveClassRescheduleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        updated_class = LiveClassService.reschedule_class(
            live_class=live_class,
            new_date=data["scheduled_date"],
            new_start_time=data["start_time"],
            new_end_time=data["end_time"],
            reason=data.get("reason", ""),
        )
        return self.success_response(
            data=LiveClassDetailSerializer(updated_class).data,
            message="Live class rescheduled successfully.",
        )


class LiveClassStartView(SuccessResponseMixin, APIView):
    """
    POST: Tutor starts the live session, triggering SMS reminder with Meet link.
    Accessible to assigned Tutor, Training Admin, or System Admin.
    """

    permission_classes = [IsTutorOrTrainingAdmin]

    def post(self, request, pk):
        try:
            live_class = LiveClass.objects.get(pk=pk)
        except LiveClass.DoesNotExist:
            return Response({"detail": "Live class not found."}, status=status.HTTP_404_NOT_FOUND)

        user = request.user
        if user.role == UserRole.TUTOR and live_class.tutor and live_class.tutor != user:
            raise PermissionDenied("You are not the designated tutor for this live class.")

        updated_class = LiveClassService.start_session(live_class, tutor=user)
        return self.success_response(
            data=LiveClassDetailSerializer(updated_class).data,
            message="Live class session started.",
        )


class LiveClassEndView(SuccessResponseMixin, APIView):
    """
    POST: Tutor completes the live session and optionally attaches cloud recording link.
    """

    permission_classes = [IsTutorOrTrainingAdmin]

    def post(self, request, pk):
        try:
            live_class = LiveClass.objects.get(pk=pk)
        except LiveClass.DoesNotExist:
            return Response({"detail": "Live class not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = LiveClassEndSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        updated_class = LiveClassService.end_session(
            live_class=live_class,
            recording_url=serializer.validated_data.get("recording_url", ""),
            tutor=request.user,
        )
        return self.success_response(
            data=LiveClassDetailSerializer(updated_class).data,
            message="Live class session completed successfully.",
        )


class LiveClassCancelView(SuccessResponseMixin, APIView):
    """
    POST: Cancel a scheduled live class (Training Admin & System Admin).
    """

    permission_classes = [IsTrainingAdminOrAbove]

    def post(self, request, pk):
        try:
            live_class = LiveClass.objects.get(pk=pk)
        except LiveClass.DoesNotExist:
            return Response({"detail": "Live class not found."}, status=status.HTTP_404_NOT_FOUND)

        reason = request.data.get("reason", "")
        cancelled_class = LiveClassService.cancel_class(live_class, reason=reason)
        return self.success_response(
            data=LiveClassDetailSerializer(cancelled_class).data,
            message="Live class cancelled.",
        )
