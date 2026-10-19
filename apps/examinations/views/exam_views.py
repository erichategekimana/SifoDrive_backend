"""
apps/examinations/views/exam_views.py
====================================
API Views for official Examination windows.
Accessible to Training Administrators and System Administrators.
Question selection is strictly disallowed — auto-drawn by engine.
"""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.accounts.constants import UserRole
from apps.core.mixins import SuccessResponseMixin
from apps.core.permissions import IsAdminLevel
from apps.examinations.serializers import AdminExamSerializer
from apps.examinations.services import ExamService


class AdminExamListView(SuccessResponseMixin, APIView):
    """
    List and create official Examination windows.
    - Training Admin: can schedule student cohort exams.
    - System Admin: full oversight.
    """
    permission_classes = [IsAuthenticated, IsAdminLevel]

    def get(self, request):
        search = request.query_params.get("search")
        cohort_id = request.query_params.get("cohort") or request.query_params.get("cohort_id")
        status_param = request.query_params.get("status")
        exam_type = request.query_params.get("exam_type")

        exams = ExamService.list_exams(
            search=search,
            cohort_id=cohort_id,
            status=status_param,
            exam_type=exam_type,
        )
        serializer = AdminExamSerializer(exams, many=True)
        return self.success_response(
            data=serializer.data,
            message="Official examinations retrieved successfully.",
        )

    def post(self, request):
        serializer = AdminExamSerializer(data=request.data)
        if not serializer.is_valid():
            return self.error_response(
                code="VALIDATION_ERROR",
                message="Invalid examination scheduling parameters.",
                errors=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        exam = ExamService.create_exam(serializer.validated_data, request.user)
        result_serializer = AdminExamSerializer(exam)
        return self.success_response(
            data=result_serializer.data,
            message="Official examination window created successfully.",
            status_code=status.HTTP_201_CREATED,
        )


class AdminExamDetailView(SuccessResponseMixin, APIView):
    """
    Retrieve, update, or delete an official Examination window.
    """
    permission_classes = [IsAuthenticated, IsAdminLevel]

    def get(self, request, pk):
        exam = ExamService.get_exam(str(pk))
        if not exam:
            return self.error_response(
                code="EXAM_NOT_FOUND",
                message="Examination window not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        serializer = AdminExamSerializer(exam)
        return self.success_response(
            data=serializer.data,
            message="Examination details retrieved.",
        )

    def patch(self, request, pk):
        exam = ExamService.get_exam(str(pk))
        if not exam:
            return self.error_response(
                code="EXAM_NOT_FOUND",
                message="Examination window not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        serializer = AdminExamSerializer(data=request.data, partial=True)
        if not serializer.is_valid():
            return self.error_response(
                code="VALIDATION_ERROR",
                message="Invalid examination update parameters.",
                errors=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        updated = ExamService.update_exam(str(pk), serializer.validated_data, request.user)
        result_serializer = AdminExamSerializer(updated)
        return self.success_response(
            data=result_serializer.data,
            message="Examination window updated successfully.",
        )

    def delete(self, request, pk):
        deleted = ExamService.delete_exam(str(pk))
        if not deleted:
            return self.error_response(
                code="EXAM_NOT_FOUND",
                message="Examination window not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return self.success_response(
            data={"id": str(pk)},
            message="Examination window deleted successfully.",
        )


class AdminExamTogglePublishView(SuccessResponseMixin, APIView):
    """
    Toggle publish state of an Examination window.
    """
    permission_classes = [IsAuthenticated, IsAdminLevel]

    def post(self, request, pk):
        exam = ExamService.toggle_publish(str(pk))
        if not exam:
            return self.error_response(
                code="EXAM_NOT_FOUND",
                message="Examination window not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        serializer = AdminExamSerializer(exam)
        new_status = "published" if exam.get("is_published") else "unpublished"
        return self.success_response(
            data=serializer.data,
            message=f"Examination window {new_status} successfully.",
        )


class AdminExamAuditView(SuccessResponseMixin, APIView):
    """
    Retrieve comprehensive audit metrics, sessions, attempts, and purchase history.
    """
    permission_classes = [IsAuthenticated, IsAdminLevel]

    def get(self, request, pk_or_type):
        audit_data = ExamService.get_exam_audit_data(str(pk_or_type))
        return self.success_response(
            data=audit_data,
            message="Exam audit metrics retrieved successfully.",
        )
