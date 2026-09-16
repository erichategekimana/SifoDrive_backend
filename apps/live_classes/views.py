"""
apps/live_classes/views.py
==========================
REST API views for Live Classes, Cohorts, and Attendance Tracking.
Enforces multi-tier permissions:
  - System Admin & Training Admin: Full cohort management and class scheduling.
  - Tutors: Session starting/ending, resource uploading, attendance marking.
  - Students: Timetable viewing, Google Meet joining, resource downloading, attendance history.
  - Guests: Strictly blocked from live classes.
"""

from datetime import date
import logging

from django.db.models import Q
from rest_framework import generics, permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.constants import UserRole
from apps.accounts.models import User
from apps.core.mixins import SuccessResponseMixin
from apps.core.permissions import (
    IsAdminLevel,
    IsStudent,
    IsStudentOrStaff,
    IsTrainingAdminOrAbove,
    IsTutorOrTrainingAdmin,
)
from .models import (
    AttendanceStatus,
    ClassAttendance,
    ClassResource,
    Cohort,
    LiveClass,
    LiveClassStatus,
)
from .serializers import (
    BatchAttendanceRecordSerializer,
    ClassAttendanceSerializer,
    ClassResourceCreateSerializer,
    ClassResourceSerializer,
    CohortAssignStudentsSerializer,
    CohortAssignTutorsSerializer,
    CohortCreateUpdateSerializer,
    CohortDetailSerializer,
    CohortListSerializer,
    LiveClassCreateUpdateSerializer,
    LiveClassDetailSerializer,
    LiveClassEndSessionSerializer,
    LiveClassListSerializer,
    LiveClassRecurringScheduleSerializer,
    LiveClassRescheduleSerializer,
    StudentAttendanceSummarySerializer,
)
from .services import AttendanceService, CohortService, LiveClassService

logger = logging.getLogger("apps.live_classes.views")


# ===========================================================================
# Cohort Views
# ===========================================================================

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
        user = self.request.user
        if user.role in [UserRole.SYSTEM_ADMIN, UserRole.TRAINING_ADMIN, UserRole.TUTOR, UserRole.BOARD_REVIEWER]:
            return Cohort.objects.all().prefetch_related("assigned_tutors", "students")
        return user.enrolled_cohorts.filter(is_active=True)

    def perform_create(self, serializer):
        data = serializer.validated_data
        cohort = CohortService.create_cohort(
            name=data["name"],
            code=data["code"],
            start_date=data["start_date"],
            end_date=data.get("end_date"),
            max_capacity=data.get("max_capacity", 50),
            schedule_description=data.get("schedule_description", ""),
            description=data.get("description", ""),
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

    def perform_destroy(self, instance):
        from rest_framework.exceptions import ValidationError
        from .services import CohortService
        can_deactivate, ongoing = CohortService.can_deactivate_cohort(instance)
        if not can_deactivate:
            raise ValidationError(
                f"Cannot deactivate cohort '{instance.name}'. There are {ongoing} active student(s) currently enrolled who have not completed or withdrawn from the course."
            )
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])


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


# ===========================================================================
# Live Class Views
# ===========================================================================

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


# ===========================================================================
# Class Resource Views
# ===========================================================================

class ClassResourceListCreateView(SuccessResponseMixin, generics.ListCreateAPIView):
    """
    GET: List supplementary materials for a live class.
    POST: Upload slide deck / add link (Tutor, Training Admin, System Admin).
    """

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsTutorOrTrainingAdmin()]
        return [IsStudentOrStaff()]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ClassResourceCreateSerializer
        return ClassResourceSerializer

    def get_queryset(self):
        return ClassResource.objects.filter(live_class_id=self.kwargs["pk"])

    def perform_create(self, serializer):
        try:
            live_class = LiveClass.objects.get(pk=self.kwargs["pk"])
        except LiveClass.DoesNotExist:
            raise ValidationError("Live class not found.")

        resource = LiveClassService.add_resource(
            live_class=live_class,
            title=serializer.validated_data["title"],
            file=serializer.validated_data.get("file"),
            external_link=serializer.validated_data.get("external_link", ""),
            description=serializer.validated_data.get("description", ""),
            uploaded_by=self.request.user,
        )
        serializer.instance = resource


class ClassResourceDetailView(SuccessResponseMixin, generics.DestroyAPIView):
    """DELETE: Remove an uploaded class resource (Tutor, Training Admin, Admin)."""

    permission_classes = [IsTutorOrTrainingAdmin]
    queryset = ClassResource.objects.all()


# ===========================================================================
# Attendance Views
# ===========================================================================

class ClassAttendanceListView(SuccessResponseMixin, generics.ListAPIView):
    """
    GET: View attendance list for a specific live class (Tutors & Admins).
    """

    permission_classes = [IsTutorOrTrainingAdmin]
    serializer_class = ClassAttendanceSerializer

    def get_queryset(self):
        return ClassAttendance.objects.filter(
            live_class_id=self.kwargs["pk"]
        ).select_related("student", "marked_by")


class ClassAttendanceBatchView(SuccessResponseMixin, APIView):
    """
    POST: Batch record/update attendance for students in a live class.
    Used by tutors after or during a session.
    """

    permission_classes = [IsTutorOrTrainingAdmin]

    def post(self, request, pk):
        try:
            live_class = LiveClass.objects.get(pk=pk)
        except LiveClass.DoesNotExist:
            return Response({"detail": "Live class not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = BatchAttendanceRecordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        records = serializer.validated_data["records"]
        count = AttendanceService.batch_record_attendance(
            live_class=live_class,
            records=records,
            marked_by=request.user,
        )
        return self.success_response(
            data={
                "live_class_id": str(live_class.id),
                "updated_count": count,
            },
            message=f"Successfully updated {count} attendance records.",
        )


class MyAttendanceSummaryView(SuccessResponseMixin, APIView):
    """
    GET: Student view of their live class attendance rate, statistics, and exam eligibility status.
    Directly answers whether student has achieved the 75% threshold needed for provisional mock exams.
    """

    permission_classes = [IsStudent]

    def get(self, request):
        summary = AttendanceService.get_student_attendance_summary(request.user)
        records = ClassAttendance.objects.filter(student=request.user).select_related("live_class")
        serializer = ClassAttendanceSerializer(records, many=True)
        return self.success_response(data={
            "summary": summary,
            "attendances": serializer.data,
        })


class StudentAttendanceDetailView(SuccessResponseMixin, APIView):
    """
    GET: Tutor or Admin view of a student's attendance records and exam readiness.
    """

    permission_classes = [IsTutorOrTrainingAdmin]

    def get(self, request, student_id):
        try:
            student = User.objects.get(id=student_id, role=UserRole.STUDENT)
        except User.DoesNotExist:
            return Response({"detail": "Student not found."}, status=status.HTTP_404_NOT_FOUND)

        summary = AttendanceService.get_student_attendance_summary(student)
        records = ClassAttendance.objects.filter(student=student).select_related("live_class")
        serializer = ClassAttendanceSerializer(records, many=True)
        return self.success_response(data={
            "student_id": str(student.id),
            "student_name": student.get_full_name(),
            "phone_number": student.phone_number,
            "summary": summary,
            "attendances": serializer.data,
        })
