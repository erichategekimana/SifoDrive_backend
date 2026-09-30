from rest_framework import generics, permissions, status
from rest_framework.response import Response

from apps.core.mixins import SuccessResponseMixin
from apps.core.permissions import IsBoardReviewer
from apps.accounts.services.reviewer_service import ReviewerService
from apps.accounts.serializers.reviewer_serializers import (
    ReviewerCertifyActionSerializer,
    ReviewerProfileSerializer,
    ReviewerQueueItemSerializer,
    ReviewerStatsSerializer,
)


class ReviewerStatsView(SuccessResponseMixin, generics.GenericAPIView):
    """
    GET /api/v1/auth/reviewer/stats/
    Returns caseload statistics for Board Reviewers.
    """
    permission_classes = [permissions.IsAuthenticated, IsBoardReviewer]

    def get(self, request, *args, **kwargs):
        stats = ReviewerService.get_reviewer_dashboard_stats(request.user)
        return self.success_response(data=stats)


class ReviewerProfileView(SuccessResponseMixin, generics.RetrieveUpdateAPIView):
    """
    GET /api/v1/auth/reviewer/profile/
    PATCH /api/v1/auth/reviewer/profile/
    Retrieve or update Board Reviewer profile.
    """
    permission_classes = [permissions.IsAuthenticated, IsBoardReviewer]
    serializer_class = ReviewerProfileSerializer

    def get_object(self):
        return ReviewerService.get_or_create_profile(self.request.user)

    def retrieve(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_object())
        return self.success_response(data=serializer.data)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return self.success_response(data=serializer.data, message="Reviewer credentials updated.")


class ReviewerQueueView(SuccessResponseMixin, generics.GenericAPIView):
    """
    GET /api/v1/auth/reviewer/queue/
    Queue of flagged candidate exam sessions requiring proctoring verification.
    """
    permission_classes = [permissions.IsAuthenticated, IsBoardReviewer]

    def get(self, request, *args, **kwargs):
        queue_items = ReviewerService.get_flagged_queue()
        serializer = ReviewerQueueItemSerializer(queue_items, many=True)
        return self.success_response(data=serializer.data)


class ReviewerCertifyView(SuccessResponseMixin, generics.GenericAPIView):
    """
    POST /api/v1/auth/reviewer/certify/
    Certify candidate official score or disqualify due to proctoring violations.
    """
    permission_classes = [permissions.IsAuthenticated, IsBoardReviewer]
    serializer_class = ReviewerCertifyActionSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = ReviewerService.certify_exam_session(
            reviewer_user=request.user,
            session_id=serializer.validated_data["session_id"],
            action=serializer.validated_data["action"],
            remarks=serializer.validated_data.get("remarks", ""),
        )
        return self.success_response(
            data=result,
            message=result["message"],
            status_code=status.HTTP_200_OK,
        )
