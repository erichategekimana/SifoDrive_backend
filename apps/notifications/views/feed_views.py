from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.mixins import SuccessResponseMixin
from apps.core.pagination import StandardResultsPagination
from apps.notifications.models import Notification
from apps.notifications.serializers import (
    NotificationPreferenceSerializer,
    NotificationSerializer,
)
from apps.notifications.services import NotificationService


class NotificationListView(SuccessResponseMixin, generics.ListAPIView):
    """
    List in-app notifications for the authenticated user.
    Supports query parameters:
      - is_read: 'true' or 'false'
      - type: Filter by NotificationType (e.g. 'PAYMENT_SUCCESS', 'EXAM_RESULT')
    """
    permission_classes = [IsAuthenticated]
    serializer_class = NotificationSerializer
    pagination_class = StandardResultsPagination

    def get_queryset(self):
        qs = Notification.objects.in_app_feed(self.request.user)
        is_read_param = self.request.query_params.get("is_read")
        if is_read_param is not None:
            if is_read_param.lower() in ("true", "1"):
                qs = qs.filter(is_read=True)
            elif is_read_param.lower() in ("false", "0"):
                qs = qs.filter(is_read=False)

        type_param = self.request.query_params.get("type")
        if type_param:
            qs = qs.filter(notification_type=type_param.upper())

        return qs


class NotificationUnreadCountView(SuccessResponseMixin, APIView):
    """
    Returns unread notification badge count for the navbar header.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        unread_count = NotificationService.get_unread_count(request.user)
        return self.success_response(
            data={"unread_count": unread_count},
            message="Unread count fetched successfully.",
        )


class NotificationMarkReadView(SuccessResponseMixin, APIView):
    """
    Mark a single notification as read.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk, *args, **kwargs):
        success = NotificationService.mark_as_read(request.user, pk)
        if not success:
            return self.error_response(
                code="NOT_FOUND",
                message="Notification not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return self.success_response(
            data={"id": str(pk), "is_read": True},
            message="Notification marked as read.",
        )


class NotificationMarkAllReadView(SuccessResponseMixin, APIView):
    """
    Mark all notifications as read for current user.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        updated_count = NotificationService.mark_all_as_read(request.user)
        return self.success_response(
            data={"updated_count": updated_count},
            message=f"Marked {updated_count} notifications as read.",
        )


class NotificationDetailView(SuccessResponseMixin, generics.RetrieveDestroyAPIView):
    """
    Retrieve or dismiss/delete a notification.
    Enforces that user owns the notification.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = NotificationSerializer

    def get_queryset(self):
        return Notification.objects.filter(recipient=self.request.user)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete()
        return self.success_response(
            data=None,
            message="Notification dismissed successfully.",
            status_code=status.HTTP_200_OK,
        )


class NotificationPreferenceView(SuccessResponseMixin, APIView):
    """
    Retrieve or update user notification preferences.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        prefs = NotificationService.get_user_preferences(request.user)
        serializer = NotificationPreferenceSerializer(prefs)
        return self.success_response(
            data=serializer.data,
            message="Preferences retrieved successfully.",
        )

    def put(self, request, *args, **kwargs):
        serializer = NotificationPreferenceSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated_prefs = NotificationService.update_user_preferences(
            request.user,
            **serializer.validated_data,
        )
        return self.success_response(
            data=NotificationPreferenceSerializer(updated_prefs).data,
            message="Preferences updated successfully.",
        )

    def patch(self, request, *args, **kwargs):
        return self.put(request, *args, **kwargs)
