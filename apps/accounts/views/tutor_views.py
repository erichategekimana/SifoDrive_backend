from rest_framework import generics, permissions
from rest_framework.response import Response

from apps.core.mixins import SuccessResponseMixin
from apps.core.permissions import IsTutor
from apps.accounts.services.tutor_service import TutorService
from apps.accounts.serializers.tutor_serializers import (
    TutorAssignedStudentSerializer,
    TutorProfileSerializer,
    TutorStatsSerializer,
)


class TutorStatsView(SuccessResponseMixin, generics.GenericAPIView):
    """
    GET /api/v1/auth/tutor/stats/
    Returns overview statistics for the Instructor Console.
    """
    permission_classes = [permissions.IsAuthenticated, IsTutor]

    def get(self, request, *args, **kwargs):
        stats = TutorService.get_tutor_dashboard_stats(request.user)
        return self.success_response(data=stats)


class TutorProfileView(SuccessResponseMixin, generics.RetrieveUpdateAPIView):
    """
    GET /api/v1/auth/tutor/profile/
    PATCH /api/v1/auth/tutor/profile/
    Retrieve or update instructor professional profile.
    """
    permission_classes = [permissions.IsAuthenticated, IsTutor]
    serializer_class = TutorProfileSerializer

    def get_object(self):
        return TutorService.get_or_create_profile(self.request.user)

    def retrieve(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_object())
        return self.success_response(data=serializer.data)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return self.success_response(data=serializer.data, message="Instructor profile updated.")


class TutorStudentsListView(SuccessResponseMixin, generics.GenericAPIView):
    """
    GET /api/v1/auth/tutor/students/
    List students assigned to this tutor with exam readiness and learning streak.
    """
    permission_classes = [permissions.IsAuthenticated, IsTutor]

    def get(self, request, *args, **kwargs):
        students = TutorService.get_assigned_students(request.user)
        serializer = TutorAssignedStudentSerializer(students, many=True)
        return self.success_response(data=serializer.data)
