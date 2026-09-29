from rest_framework import serializers

from apps.notifications.models import (
    Notification,
    NotificationChannel,
    NotificationPreference,
    NotificationPriority,
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
