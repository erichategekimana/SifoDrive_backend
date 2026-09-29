from rest_framework import serializers

from apps.notifications.models import NotificationTemplate


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
