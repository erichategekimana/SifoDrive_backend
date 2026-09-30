from rest_framework import generics, permissions, status
from rest_framework.response import Response

from apps.core.mixins import SuccessResponseMixin
from apps.core.permissions import IsEnterpriseAdmin
from apps.accounts.services.enterprise_service import EnterpriseService
from apps.accounts.serializers.enterprise_serializers import (
    EnterpriseBulkEnrollSerializer,
    EnterpriseProfileSerializer,
    EnterpriseStatsSerializer,
)


class EnterpriseStatsView(SuccessResponseMixin, generics.GenericAPIView):
    """
    GET /api/v1/auth/enterprise/stats/
    Returns driving school lab concurrency, seat allocation, and student stats.
    """
    permission_classes = [permissions.IsAuthenticated, IsEnterpriseAdmin]

    def get(self, request, *args, **kwargs):
        stats = EnterpriseService.get_enterprise_dashboard_stats(request.user)
        return self.success_response(data=stats)


class EnterpriseProfileView(SuccessResponseMixin, generics.RetrieveUpdateAPIView):
    """
    GET /api/v1/auth/enterprise/profile/
    PATCH /api/v1/auth/enterprise/profile/
    Retrieve or update driving school institutional profile.
    """
    permission_classes = [permissions.IsAuthenticated, IsEnterpriseAdmin]
    serializer_class = EnterpriseProfileSerializer

    def get_object(self):
        return EnterpriseService.get_or_create_profile(self.request.user)

    def retrieve(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_object())
        return self.success_response(data=serializer.data)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return self.success_response(data=serializer.data, message="Driving school profile updated.")


class EnterpriseStudentsListView(SuccessResponseMixin, generics.GenericAPIView):
    """
    GET /api/v1/auth/enterprise/students/
    List students affiliated with this driving school.
    """
    permission_classes = [permissions.IsAuthenticated, IsEnterpriseAdmin]

    def get(self, request, *args, **kwargs):
        students = EnterpriseService.get_school_students(request.user)
        return self.success_response(data=students)


class EnterpriseBulkEnrollView(SuccessResponseMixin, generics.GenericAPIView):
    """
    POST /api/v1/auth/enterprise/students/bulk/
    Batch-enroll students under this driving school.
    """
    permission_classes = [permissions.IsAuthenticated, IsEnterpriseAdmin]
    serializer_class = EnterpriseBulkEnrollSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = EnterpriseService.bulk_enroll_students(
            enterprise_user=request.user,
            students_data=serializer.validated_data["students"],
        )
        return self.success_response(
            data=result,
            message=f"Bulk intake processed: {result['created_count']} created, {result['skipped_count']} skipped.",
            status_code=status.HTTP_201_CREATED,
        )
