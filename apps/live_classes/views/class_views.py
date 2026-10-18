from datetime import date, time
import logging

from django.db.models import Q
from django.utils import timezone
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
from apps.live_classes.models import Cohort, LiveClass, LiveClassSchedule
from apps.live_classes.models.choices import LiveClassStatus
from apps.live_classes.serializers import (
    LiveClassCreateUpdateSerializer,
    LiveClassDetailSerializer,
    LiveClassEndSessionSerializer,
    LiveClassListSerializer,
    LiveClassRecurringScheduleSerializer,
    LiveClassRescheduleSerializer,
    LiveClassScheduleSerializer,
    LiveClassScheduleUpdateSerializer,
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
        master_schedule = LiveClassService.schedule_recurring_classes(
            **serializer.validated_data,
            created_by=request.user,
        )
        return self.success_response(
            data=LiveClassScheduleSerializer(master_schedule).data,
            message=f"Successfully scheduled class '{master_schedule.title}' with {master_schedule.total_sessions_count} sessions.",
        )


class LiveClassScheduleListCreateView(SuccessResponseMixin, generics.ListCreateAPIView):
    """
    GET: List master live class schedules (1 row per schedule offering).
    POST: Create a new class schedule (single or recurring).
    """

    serializer_class = LiveClassScheduleSerializer

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsTrainingAdminOrAbove()]
        return [IsStudentOrStaff()]

    def get_queryset(self):
        user = self.request.user
        qs = LiveClassSchedule.objects.select_related("cohort", "tutor", "created_by").filter(is_active=True)

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

        cohort_id = self.request.query_params.get("cohort")
        if cohort_id:
            qs = qs.filter(cohort_id=cohort_id)
        return qs.order_by("-created_at")

    def create(self, request, *args, **kwargs):
        schedule_mode = request.data.get("schedule_mode")
        if schedule_mode == "SINGLE" or ("scheduled_date" in request.data and not request.data.get("days_of_week") and not request.data.get("period_months")):
            serializer = LiveClassCreateUpdateSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            data = serializer.validated_data
            live_class = LiveClassService.schedule_class(
                **data,
                created_by=request.user,
            )
            master_schedule = live_class.schedule
            return self.success_response(
                data=LiveClassScheduleSerializer(master_schedule).data if master_schedule else LiveClassDetailSerializer(live_class).data,
                message=f"Successfully scheduled class '{live_class.title}'.",
                status_code=201,
            )

        serializer = LiveClassRecurringScheduleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        master_schedule = LiveClassService.schedule_recurring_classes(
            **serializer.validated_data,
            created_by=request.user,
        )
        return self.success_response(
            data=LiveClassScheduleSerializer(master_schedule).data,
            message=f"Successfully created schedule '{master_schedule.title}'.",
            status_code=201,
        )


class LiveClassScheduleDetailView(SuccessResponseMixin, APIView):
    """
    GET: View master schedule details and all associated session dates.
    PATCH/PUT: Update schedule attributes and synchronize future scheduled sessions.
    DELETE: Soft-delete schedule and cancel all associated session instances.
    """

    def get_permissions(self):
        if self.request.method in ["PATCH", "PUT", "DELETE"]:
            return [IsTrainingAdminOrAbove()]
        return [IsStudentOrStaff()]

    def get(self, request, pk, *args, **kwargs):
        try:
            schedule = LiveClassSchedule.objects.select_related("cohort", "tutor", "created_by").get(id=pk, is_active=True)
        except LiveClassSchedule.DoesNotExist:
            return self.error_response("Schedule not found.", status_code=404)

        user = request.user
        if user.role == UserRole.STUDENT and schedule.cohort:
            if not user.enrolled_cohorts.filter(id=schedule.cohort_id).exists():
                raise PermissionDenied("You are not enrolled in the cohort for this schedule.")
        elif user.role == UserRole.TUTOR and schedule.cohort and schedule.tutor != user:
            if not user.assigned_cohorts.filter(id=schedule.cohort_id).exists():
                raise PermissionDenied("You are not assigned to the cohort for this schedule.")

        schedule_data = LiveClassScheduleSerializer(schedule).data
        sessions = schedule.sessions.all().order_by("scheduled_date", "start_time")
        schedule_data["sessions"] = LiveClassListSerializer(sessions, many=True).data
        return self.success_response(data=schedule_data)

    def patch(self, request, pk, *args, **kwargs):
        serializer = LiveClassScheduleUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            updated_schedule = LiveClassService.update_schedule(
                schedule_id=str(pk),
                **serializer.validated_data,
                updated_by=request.user,
            )
            return self.success_response(
                data=LiveClassScheduleSerializer(updated_schedule).data,
                message="Schedule updated successfully.",
            )
        except LiveClassSchedule.DoesNotExist:
            return self.error_response("Schedule not found.", status_code=404)

    def delete(self, request, pk, *args, **kwargs):
        try:
            LiveClassService.delete_schedule(schedule_id=str(pk), deleted_by=request.user)
            return self.success_response(message="Schedule and all associated class sessions deleted.")
        except LiveClassSchedule.DoesNotExist:
            return self.error_response("Schedule not found.", status_code=404)


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
        if self.request.method == "DELETE":
            return [IsTrainingAdminOrAbove()]
        if self.request.method in ["PATCH", "PUT"]:
            return [IsTutorOrTrainingAdmin()]
        return [IsStudentOrStaff()]

    def get_serializer_class(self):
        if self.request.method in ["PATCH", "PUT"]:
            return LiveClassCreateUpdateSerializer
        return LiveClassDetailSerializer

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", True)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return self.success_response(
            data=LiveClassDetailSerializer(instance).data,
            message="Live class updated successfully.",
        )

    def perform_destroy(self, instance):
        instance.delete(deleted_by=self.request.user)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return self.success_response(message="Live class deleted successfully.")


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


class LiveClassRecordingView(SuccessResponseMixin, APIView):
    """
    POST: Tutor or Training Admin posts or updates the cloud recording URL for a live class session.
    Students can subsequently watch the recording.
    """

    permission_classes = [IsTutorOrTrainingAdmin]

    def post(self, request, pk):
        try:
            live_class = LiveClass.objects.get(pk=pk)
        except LiveClass.DoesNotExist:
            return Response({"detail": "Live class not found."}, status=status.HTTP_404_NOT_FOUND)

        user = request.user
        if user.role == UserRole.TUTOR and live_class.tutor and live_class.tutor != user:
            if not live_class.cohort or not live_class.cohort.assigned_tutors.filter(id=user.id).exists():
                raise PermissionDenied("You are not the designated tutor for this live class.")

        recording_url = request.data.get("recording_url", "").strip()
        if not recording_url:
            return Response({"detail": "Recording URL is required."}, status=status.HTTP_400_BAD_REQUEST)

        live_class.recording_url = recording_url
        if "notes" in request.data and request.data["notes"]:
            live_class.notes = request.data["notes"].strip()

        if live_class.status != LiveClassStatus.COMPLETED and (live_class.is_past or recording_url):
            live_class.status = LiveClassStatus.COMPLETED
            if not live_class.actual_ended_at:
                live_class.actual_ended_at = timezone.now()

        live_class.save(update_fields=["recording_url", "notes", "status", "actual_ended_at", "updated_at"])

        return self.success_response(
            data=LiveClassDetailSerializer(live_class).data,
            message="Class recording posted successfully.",
        )


class LiveClassDirectRecordingCreateView(SuccessResponseMixin, APIView):
    """
    POST /api/v1/live-classes/recordings/
    Directly add or publish a recording for a live class.
    Tutors and Training Admins can specify:
      - session_id (optional, updates existing session)
      - title
      - scheduled_date / date
      - start_time / end_time
      - recording_url / google_link (Google Drive / Meet URL)
      - cohort_id / cohort (optional)
      - notes (optional)
    """

    permission_classes = [IsTutorOrTrainingAdmin]

    def post(self, request):
        user = request.user
        class_id = request.data.get("session_id") or request.data.get("class_id")
        recording_url = (
            request.data.get("recording_url", "").strip()
            or request.data.get("google_link", "").strip()
        )

        if not recording_url:
            return Response(
                {"detail": "Google recording link is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        scheduled_date_str = request.data.get("scheduled_date") or request.data.get("date")
        if not scheduled_date_str:
            scheduled_date = date.today()
        else:
            try:
                scheduled_date = date.fromisoformat(str(scheduled_date_str).strip())
            except ValueError:
                scheduled_date = date.today()

        # If class_id was not explicitly passed, check if an awaiting session exists on this date
        if not class_id:
            cohort_id = request.data.get("cohort") or request.data.get("cohort_id")
            awaiting_query = LiveClass.objects.filter(
                scheduled_date=scheduled_date,
                recording_url="",
            )
            if cohort_id:
                awaiting_query = awaiting_query.filter(cohort_id=cohort_id)
            elif user.role == UserRole.TUTOR:
                tutor_cohort_ids = list(user.assigned_cohorts.filter(is_active=True).values_list("id", flat=True))
                awaiting_query = awaiting_query.filter(Q(tutor=user) | Q(cohort_id__in=tutor_cohort_ids))

            matched_session = awaiting_query.first()
            if matched_session:
                class_id = str(matched_session.id)

        # 1. If explicit session_id provided or matched on date, attach to that session
        if class_id:
            try:
                live_class = LiveClass.objects.get(pk=class_id)
                live_class.recording_url = recording_url
                if request.data.get("title"):
                    live_class.title = request.data["title"].strip()
                if request.data.get("notes"):
                    live_class.notes = request.data["notes"].strip()
                live_class.status = LiveClassStatus.COMPLETED
                if not live_class.actual_ended_at:
                    live_class.actual_ended_at = timezone.now()
                live_class.save()
                return self.success_response(
                    data=LiveClassDetailSerializer(live_class).data,
                    message="Class recording published successfully.",
                    status_code=200,
                )
            except LiveClass.DoesNotExist:
                pass

        title = request.data.get("title", "").strip() or f"Class Recording - {scheduled_date.strftime('%b %d, %Y')}"

        start_time_str = request.data.get("start_time") or "14:00"
        end_time_str = request.data.get("end_time") or "15:30"

        try:
            start_time = time.fromisoformat(str(start_time_str)[:5])
        except ValueError:
            start_time = time(14, 0)

        try:
            end_time = time.fromisoformat(str(end_time_str)[:5])
        except ValueError:
            end_time = time(15, 30)

        cohort_id = request.data.get("cohort") or request.data.get("cohort_id")
        cohort = None
        if cohort_id:
            cohort = Cohort.objects.filter(id=cohort_id).first()
        elif user.role == UserRole.TUTOR:
            cohort = user.assigned_cohorts.filter(is_active=True).first()

        tutor = user if user.role == UserRole.TUTOR else None

        master_schedule = LiveClassSchedule.objects.create(
            title=title,
            topic=request.data.get("topic", "").strip(),
            cohort=cohort,
            tutor=tutor,
            schedule_mode="SINGLE",
            days_of_week=[scheduled_date.weekday()],
            start_time=start_time,
            end_time=end_time,
            start_date=scheduled_date,
            end_date=scheduled_date,
            period_months=1,
            period_unit="months",
            google_meet_url=recording_url,
            is_published=True,
            notes=request.data.get("notes", "").strip(),
            created_by=user,
        )

        live_class = LiveClass.objects.create(
            title=title,
            topic=request.data.get("topic", "").strip(),
            cohort=cohort,
            tutor=tutor,
            schedule=master_schedule,
            scheduled_date=scheduled_date,
            start_time=start_time,
            end_time=end_time,
            google_meet_url=recording_url,
            recording_url=recording_url,
            status=LiveClassStatus.COMPLETED,
            is_published=True,
            notes=request.data.get("notes", "").strip(),
            actual_started_at=timezone.now(),
            actual_ended_at=timezone.now(),
            created_by=user,
        )

        return self.success_response(
            data=LiveClassDetailSerializer(live_class).data,
            message="Class recording published successfully.",
            status_code=201,
        )

