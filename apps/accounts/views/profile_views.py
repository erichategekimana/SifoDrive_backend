"""
apps/accounts/views/profile_views.py
======================================
User self-service profile views.

Endpoints:
  GET  /auth/me/                 → UserProfileView (retrieve)
  PATCH /auth/me/                → UserProfileView (update)
  GET  /auth/me/student-profile/ → StudentProfileView (retrieve)
  PATCH /auth/me/student-profile/ → StudentProfileView (update)
"""

import logging

from rest_framework import generics, permissions
from rest_framework.exceptions import NotFound

from apps.core.mixins import SuccessResponseMixin
from apps.accounts.serializers import (
    StudentProfileSerializer,
    UserProfileSerializer,
)

logger = logging.getLogger(__name__)


class UserProfileView(SuccessResponseMixin, generics.RetrieveUpdateAPIView):
    """
    GET  /api/v1/auth/me/  — Retrieve authenticated user's profile.
    PATCH /api/v1/auth/me/ — Update profile fields (first_name, last_name, email,
                              profile_photo, date_of_birth).
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserProfileSerializer

    def get_object(self):
        return self.request.user

    def retrieve(self, request, *args, **kwargs):
        return self.success_response(data=self.get_serializer(self.get_object()).data)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return self.success_response(data=serializer.data, message="Profile updated.")


class StudentProfileView(SuccessResponseMixin, generics.RetrieveUpdateAPIView):
    """
    GET  /api/v1/auth/me/student-profile/
    PATCH /api/v1/auth/me/student-profile/

    Student-specific extended profile: preferred language, license category, streak.
    Only accessible to authenticated users with a StudentProfile (STUDENT role).
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = StudentProfileSerializer

    def get_object(self):
        try:
            return self.request.user.student_profile
        except AttributeError:
            raise NotFound("Student profile not found. Are you registered as a student?")

    def retrieve(self, request, *args, **kwargs):
        return self.success_response(data=self.get_serializer(self.get_object()).data)

    def update(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_object(), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return self.success_response(data=serializer.data, message="Student profile updated.")


class StudentEligibilityView(SuccessResponseMixin, generics.GenericAPIView):
    """
    GET /api/v1/auth/me/student-profile/eligibility/
    Evaluates 3-pillar criteria: tuition paid, live class attendance >= 75%, foundational modules 100%.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        from apps.accounts.services.student_service import StudentService
        data = StudentService.check_exam_eligibility(request.user)
        return self.success_response(data=data)

