from rest_framework import serializers
from apps.lms.models import HelpTicket, TicketCategory, TicketPriority, TicketRecipientRole, TicketStatus


class HelpTicketSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.full_name", read_only=True)
    user_phone = serializers.CharField(source="user.phone_number", read_only=True)
    user_role = serializers.CharField(source="user.role", read_only=True)
    assigned_to_name = serializers.CharField(source="assigned_to.full_name", read_only=True, allow_null=True)

    class Meta:
        model = HelpTicket
        fields = [
            "id",
            "user",
            "user_name",
            "user_phone",
            "user_role",
            "recipient_role",
            "category",
            "subject",
            "message",
            "priority",
            "status",
            "assigned_to",
            "assigned_to_name",
            "response",
            "resolved_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "user",
            "user_name",
            "user_phone",
            "user_role",
            "status",
            "assigned_to",
            "assigned_to_name",
            "response",
            "resolved_at",
            "created_at",
            "updated_at",
        ]


class HelpTicketCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = HelpTicket
        fields = [
            "recipient_role",
            "category",
            "subject",
            "message",
            "priority",
        ]


class HelpTicketResolveSerializer(serializers.Serializer):
    response = serializers.CharField(required=True)
    status = serializers.ChoiceField(
        choices=[TicketStatus.RESOLVED, TicketStatus.CLOSED],
        default=TicketStatus.RESOLVED,
    )
