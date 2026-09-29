from rest_framework import serializers

from apps.core.utils import PhoneNumberUtils
from apps.notifications.models import NotificationType, SMSNotification


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
