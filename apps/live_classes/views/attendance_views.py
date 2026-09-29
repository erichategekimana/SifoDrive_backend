from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.constants import UserRole
from apps.accounts.models import User
from apps.core.mixins import SuccessResponseMixin
from apps.core.permissions import (
    IsStudent,
    IsTutorOrTrainingAdmin,
)
from apps.live_classes.models import ClassAttendance, LiveClass
from apps.live_classes.serializers import (
    BatchAttendanceRecordSerializer,
    ClassAttendanceSerializer,
)
from apps.live_classes.services import AttendanceService


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
