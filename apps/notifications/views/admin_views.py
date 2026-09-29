from django.conf import settings
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.mixins import SuccessResponseMixin
from apps.core.pagination import StandardResultsPagination
from apps.core.permissions import IsAdminLevel, IsSystemAdmin
from apps.notifications.models import (
    NotificationChannel,
    NotificationTemplate,
    NotificationType,
    SMSNotification,
)
from apps.notifications.serializers import (
    BroadcastNotificationSerializer,
    DirectSMSRequestSerializer,
    NotificationTemplateSerializer,
    SMSNotificationSerializer,
)
from apps.notifications.services import SMSDispatcherService


class AdminSMSLogListView(SuccessResponseMixin, generics.ListAPIView):
    """
    Admin audit view for SMS transmission logs.
    Restricted to Enterprise Admin, Board Reviewer, and System Admin.
    """
    permission_classes = [IsAuthenticated, IsAdminLevel]
    serializer_class = SMSNotificationSerializer
    pagination_class = StandardResultsPagination

    def get_queryset(self):
        qs = SMSNotification.objects.all().order_by("-created_at")
        phone = self.request.query_params.get("phone")
        if phone:
            qs = qs.filter(recipient_phone__icontains=phone)

        msg_status = self.request.query_params.get("status")
        if msg_status:
            qs = qs.filter(status=msg_status.upper())

        provider = self.request.query_params.get("provider")
        if provider:
            qs = qs.filter(provider__iexact=provider)

        msg_type = self.request.query_params.get("type")
        if msg_type:
            qs = qs.filter(message_type=msg_type.upper())

        return qs


class AdminSMSLogDetailView(SuccessResponseMixin, generics.RetrieveAPIView):
    """
    Detailed view of a single SMS transmission attempt.
    """
    permission_classes = [IsAuthenticated, IsAdminLevel]
    serializer_class = SMSNotificationSerializer
    queryset = SMSNotification.objects.all()


class AdminTemplateListCreateView(SuccessResponseMixin, generics.ListCreateAPIView):
    """
    List and create message templates.
    """
    permission_classes = [IsAuthenticated, IsAdminLevel]
    serializer_class = NotificationTemplateSerializer
    queryset = NotificationTemplate.objects.all().order_by("template_code", "language")


class AdminTemplateDetailView(SuccessResponseMixin, generics.RetrieveUpdateDestroyAPIView):
    """
    Retrieve, update or delete a message template.
    """
    permission_classes = [IsAuthenticated, IsAdminLevel]
    serializer_class = NotificationTemplateSerializer
    queryset = NotificationTemplate.objects.all()


class AdminBroadcastView(SuccessResponseMixin, APIView):
    """
    Administrative mass announcement dispatcher.
    Supports role-based, cohort-based, or platform-wide broadcasts via SMS and In-App.
    Requires System Administrator privileges.
    """
    permission_classes = [IsAuthenticated, IsSystemAdmin]

    def post(self, request, *args, **kwargs):
        serializer = BroadcastNotificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        audience = data.get("audience", "ALL").upper()
        cohort_id = data.get("cohort_id")
        target_role = data.get("target_role")
        channel = data.get("channel", NotificationChannel.SMS)

        from apps.accounts.models import User
        from apps.notifications.tasks import send_bulk_notification_task

        if audience == "COHORT" and cohort_id:
            from apps.live_classes.models import Cohort
            try:
                cohort = Cohort.objects.get(id=cohort_id)
                users = cohort.students.filter(is_active=True)
            except (Cohort.DoesNotExist, Exception):
                users = User.objects.none()
        elif audience == "STUDENTS" or target_role == "STUDENT":
            users = User.objects.filter(role="STUDENT", is_active=True)
        elif audience == "GUESTS" or target_role == "GUEST":
            users = User.objects.filter(role="GUEST", is_active=True)
        elif audience == "TUTORS" or target_role == "TUTOR":
            users = User.objects.filter(role="TUTOR", is_active=True)
        elif target_role:
            users = User.objects.filter(role=target_role, is_active=True)
        else:
            users = User.objects.filter(is_active=True)

        if channel == NotificationChannel.SMS:
            users = users.exclude(phone_number__isnull=True).exclude(phone_number="")

        recipient_ids = list(users.values_list("id", flat=True))
        recipient_count = len(recipient_ids)

        if recipient_count > 0:
            send_bulk_notification_task.delay(
                recipient_ids=[str(uid) for uid in recipient_ids],
                title=data["title"],
                body=data["body"],
                title_rw=data.get("title_rw", ""),
                body_rw=data.get("body_rw", ""),
                channel=channel,
                priority=data["priority"],
                action_url=data.get("action_url", ""),
            )

        return self.accepted_response(
            data={"queued_recipients": recipient_count, "audience": audience, "channel": channel},
            message=f"Broadcast queued for {recipient_count} recipients.",
        )


class AdminTestSMSView(SuccessResponseMixin, APIView):
    """
    Direct single SMS dispatch endpoint to send messages via Rwanda gateway (Pindo).
    Restricted to System Administrators.
    """
    permission_classes = [IsAuthenticated, IsSystemAdmin]

    def post(self, request, *args, **kwargs):
        serializer = DirectSMSRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        result = SMSDispatcherService.send_sms(
            phone_number=data["phone_number"],
            message=data["message"],
            message_type=data.get("message_type", NotificationType.GENERAL),
        )

        return self.success_response(
            data={
                "success": result.success,
                "message_id": result.message_id,
                "status": result.status,
                "error_message": result.error_message,
                "raw_response": result.raw_response,
            },
            message="SMS message dispatched successfully." if result.success else f"SMS gateway returned error: {result.error_message}",
            status_code=status.HTTP_200_OK if result.success else status.HTTP_400_BAD_REQUEST,
        )


class AdminGatewayStatusView(SuccessResponseMixin, APIView):
    """
    Operational diagnostic endpoint to check Pindo / SMS gateway connectivity.
    Restricted to Admin Level.
    """
    permission_classes = [IsAuthenticated, IsAdminLevel]

    def get(self, request, *args, **kwargs):
        from apps.notifications.providers import get_sms_provider
        provider = get_sms_provider()
        if hasattr(provider, "check_gateway_connectivity"):
            diag = provider.check_gateway_connectivity()
        else:
            diag = {
                "connected": True,
                "provider": provider.get_provider_name(),
                "endpoint": getattr(settings, "SMS_GATEWAY_URL", ""),
                "sender_id": getattr(settings, "SMS_SENDER_ID", ""),
            }
        return self.success_response(data=diag, message="SMS Gateway status retrieved.")


class AdminSMSRetryView(SuccessResponseMixin, APIView):
    """
    Retry sending a previously failed or pending SMS from the audit log.
    Restricted to System Administrators.
    """
    permission_classes = [IsAuthenticated, IsSystemAdmin]

    def post(self, request, pk, *args, **kwargs):
        try:
            sms_log = SMSNotification.objects.get(id=pk)
        except SMSNotification.DoesNotExist:
            return self.error_response(code="NOT_FOUND", message="SMS log record not found.", status_code=status.HTTP_404_NOT_FOUND)

        result = SMSDispatcherService.send_sms(
            phone_number=sms_log.recipient_phone,
            message=sms_log.message_body,
            message_type=sms_log.message_type,
            parent_notification=sms_log.notification,
        )

        sms_log.retry_count += 1
        if result.success:
            sms_log.mark_sent(result.message_id or "", result.raw_response)
        else:
            sms_log.mark_failed(result.error_message or "Retry failed", result.raw_response)

        return self.success_response(
            data=SMSNotificationSerializer(sms_log).data,
            message="SMS retry dispatched." if result.success else f"SMS retry failed: {result.error_message}",
            status_code=status.HTTP_200_OK if result.success else status.HTTP_400_BAD_REQUEST,
        )
