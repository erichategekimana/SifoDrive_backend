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
    pagination_class = None

    def get_queryset(self):
        return ClassAttendance.objects.filter(
            live_class_id=self.kwargs["pk"]
        ).select_related("student", "marked_by")

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        return self.success_response(data=serializer.data)


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
        summary = AttendanceService.get_student_attendance_summary(request.user, for_student_view=True)
        records = ClassAttendance.objects.filter(student=request.user).select_related("live_class")
        serializer = ClassAttendanceSerializer(records, many=True, context={"request": request, "for_student": True})
        return self.success_response(data={
            "summary": summary,
            "attendances": serializer.data,
        })


class StudentAttendanceDetailView(SuccessResponseMixin, APIView):
    """
    GET: Tutor or Admin view of a student's attendance records and exam readiness.
    Preserves raw EXCUSED status so tutors and admins can audit that it was an excuse.
    """

    permission_classes = [IsTutorOrTrainingAdmin]

    def get(self, request, student_id):
        try:
            student = User.objects.get(id=student_id, role=UserRole.STUDENT)
        except User.DoesNotExist:
            return Response({"detail": "Student not found."}, status=status.HTTP_404_NOT_FOUND)

        summary = AttendanceService.get_student_attendance_summary(student, for_student_view=False)
        records = ClassAttendance.objects.filter(student=student).select_related("live_class")
        serializer = ClassAttendanceSerializer(records, many=True, context={"request": request, "for_student": False})
        return self.success_response(data={
            "student_id": str(student.id),
            "student_name": student.get_full_name(),
            "phone_number": student.phone_number,
            "profile_photo": request.build_absolute_uri(student.profile_photo.url) if student.profile_photo else None,
            "summary": summary,
            "attendances": serializer.data,
        })
