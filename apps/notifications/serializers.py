"""
apps/notifications/serializers.py
=================================
Serializers for In-App Notifications feed, user preferences,
and administrative broadcast & template management.
"""

from rest_framework import serializers

from apps.core.utils import PhoneNumberUtils
from apps.notifications.models import (
    Notification,
    NotificationChannel,
    NotificationPreference,
    NotificationPriority,
    NotificationTemplate,
    NotificationType,
    SMSNotification,
)


class NotificationSerializer(serializers.ModelSerializer):
    """
    Public / Authenticated user serializer for in-app notification inbox.
    Supplies localized title and body automatically based on user's preferred language.
    """

    localized_title = serializers.SerializerMethodField()
    localized_body = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = [
            "id",
            "notification_type",
            "channel",
            "priority",
            "title",
            "title_rw",
            "body",
            "body_rw",
            "localized_title",
            "localized_body",
            "action_url",
            "is_read",
            "read_at",
            "status",
            "metadata",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "notification_type",
            "channel",
            "priority",
            "title",
            "title_rw",
            "body",
            "body_rw",
            "action_url",
            "read_at",
            "status",
            "metadata",
            "created_at",
        ]

    def _get_lang(self) -> str:
        request = self.context.get("request")
        if request and request.user and request.user.is_authenticated:
            try:
                return request.user.notification_preferences.preferred_language
            except Exception:
                pass
        return "rw"

    def get_localized_title(self, obj: Notification) -> str:
        return obj.get_localized_title(self._get_lang())

    def get_localized_body(self, obj: Notification) -> str:
        return obj.get_localized_body(self._get_lang())


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    """Allows users to adjust their personal notification channels and language."""

    class Meta:
        model = NotificationPreference
        fields = [
            "sms_enabled",
            "in_app_enabled",
            "email_enabled",
            "exam_alerts",
            "booking_alerts",
            "promo_alerts",
            "preferred_language",
        ]


class SMSNotificationSerializer(serializers.ModelSerializer):
    """Administrative serializer for reviewing outbound SMS logs and gateway health."""

    phone_obfuscated = serializers.SerializerMethodField()

    class Meta:
        model = SMSNotification
        fields = [
            "id",
            "recipient_phone",
            "phone_obfuscated",
            "message_type",
            "message_body",
            "sender_id",
            "provider",
            "provider_message_id",
            "status",
            "retry_count",
            "error_message",
            "provider_response",
            "sent_at",
            "delivered_at",
            "created_at",
        ]
        read_only_fields = fields

    def get_phone_obfuscated(self, obj: SMSNotification) -> str:
        return PhoneNumberUtils.obfuscate(obj.recipient_phone)


class NotificationTemplateSerializer(serializers.ModelSerializer):
    """Administrative CRUD serializer for message templates."""

    class Meta:
        model = NotificationTemplate
        fields = [
            "id",
            "template_code",
            "notification_type",
            "channel",
            "language",
            "title_template",
            "body_template",
            "is_active",
            "description",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class BroadcastNotificationSerializer(serializers.Serializer):
    """Payload validation for administrative mass broadcast announcements and SMS campaigns."""

    title = serializers.CharField(max_length=255, required=False, default="Sifo Drive Announcement")
    body = serializers.CharField(required=False, allow_blank=True)
    message = serializers.CharField(required=False, allow_blank=True)
    title_rw = serializers.CharField(max_length=255, required=False, allow_blank=True)
    body_rw = serializers.CharField(required=False, allow_blank=True)
    audience = serializers.CharField(required=False, default="ALL")
    cohort_id = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    target_role = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    channel = serializers.ChoiceField(
        choices=NotificationChannel.choices,
        default=NotificationChannel.SMS,
    )
    priority = serializers.ChoiceField(
        choices=NotificationPriority.choices,
        default=NotificationPriority.NORMAL,
    )
    action_url = serializers.CharField(max_length=500, required=False, allow_blank=True)

    def validate(self, attrs):
        content = attrs.get("message") or attrs.get("body")
        if not content or not content.strip():
            raise serializers.ValidationError({"message": "Message body is required."})
        attrs["body"] = content.strip()
        attrs["message"] = content.strip()
        if not attrs.get("title"):
            attrs["title"] = "Sifo Drive Announcement"
        return attrs


class DirectSMSRequestSerializer(serializers.Serializer):
    """Payload validation for manual admin SMS test tool."""

    phone_number = serializers.CharField(max_length=25)
    message = serializers.CharField(max_length=480)
    message_type = serializers.ChoiceField(
        choices=NotificationType.choices,
        default=NotificationType.GENERAL,
    )

    def validate_phone_number(self, value):
        normalized = PhoneNumberUtils.normalize(value, default_region="RW")
        if not normalized:
            raise serializers.ValidationError("Invalid Rwandan phone number format.")
        return normalized
