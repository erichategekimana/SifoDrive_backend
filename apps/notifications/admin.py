"""
apps/notifications/admin.py
===========================
Django Admin site integration for Notifications, SMS transmission audit logs,
dynamic templates, and user notification preferences.
"""

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from apps.core.utils import PhoneNumberUtils
from apps.notifications.models import (
    Notification,
    NotificationPreference,
    NotificationTemplate,
    SMSNotification,
)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = [
        "id_short",
        "recipient",
        "recipient_phone",
        "notification_type",
        "channel",
        "priority_badge",
        "is_read",
        "status_badge",
        "created_at",
    ]
    list_filter = [
        "is_read",
        "channel",
        "notification_type",
        "priority",
        "status",
        "created_at",
    ]
    search_fields = [
        "recipient__phone_number",
        "recipient__first_name",
        "recipient__last_name",
        "recipient_phone",
        "title",
        "body",
    ]
    readonly_fields = [
        "id",
        "created_at",
        "updated_at",
        "read_at",
        "sent_at",
    ]
    fieldsets = (
        (_("Destination & Type"), {
            "fields": ("recipient", "recipient_phone", "recipient_email", "notification_type", "channel", "priority")
        }),
        (_("Content (Bilingual)"), {
            "fields": ("title", "title_rw", "body", "body_rw", "action_url")
        }),
        (_("Status & Delivery"), {
            "fields": ("status", "is_read", "read_at", "sent_at", "metadata")
        }),
        (_("Audit Metadata"), {
            "fields": ("id", "created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    @admin.display(description=_("ID"))
    def id_short(self, obj):
        return str(obj.id)[:8]

    @admin.display(description=_("Priority"))
    def priority_badge(self, obj):
        colors = {
            "LOW": "#6c757d",
            "NORMAL": "#0d6efd",
            "HIGH": "#fd7e14",
            "URGENT": "#dc3545",
        }
        color = colors.get(obj.priority, "#6c757d")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 11px;">{}</span>',
            color,
            obj.priority,
        )

    @admin.display(description=_("Status"))
    def status_badge(self, obj):
        colors = {
            "PENDING": "#ffc107",
            "QUEUED": "#0dcaf0",
            "SENT": "#0d6efd",
            "DELIVERED": "#198754",
            "READ": "#20c997",
            "FAILED": "#dc3545",
            "CANCELLED": "#6c757d",
        }
        color = colors.get(obj.status, "#6c757d")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 6px; border-radius: 4px; font-size: 11px;">{}</span>',
            color,
            obj.status,
        )


@admin.register(SMSNotification)
class SMSNotificationAdmin(admin.ModelAdmin):
    list_display = [
        "id_short",
        "phone_masked",
        "message_type",
        "provider",
        "status_badge",
        "provider_message_id",
        "created_at",
    ]
    list_filter = [
        "status",
        "provider",
        "message_type",
        "created_at",
    ]
    search_fields = [
        "recipient_phone",
        "provider_message_id",
        "message_body",
    ]
    readonly_fields = [
        "id",
        "notification",
        "recipient_phone",
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
        "updated_at",
    ]

    def has_add_permission(self, request):
        # SMS logs are strictly append-only by the system
        return False

    def has_delete_permission(self, request, obj=None):
        # Prevent manual deletion from admin
        return False

    @admin.display(description=_("ID"))
    def id_short(self, obj):
        return str(obj.id)[:8]

    @admin.display(description=_("Recipient Phone"))
    def phone_masked(self, obj):
        return PhoneNumberUtils.obfuscate(obj.recipient_phone)

    @admin.display(description=_("Status"))
    def status_badge(self, obj):
        colors = {
            "PENDING": "#ffc107",
            "SENT": "#0d6efd",
            "DELIVERED": "#198754",
            "FAILED": "#dc3545",
        }
        color = colors.get(obj.status, "#6c757d")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 11px;">{}</span>',
            color,
            obj.status,
        )


@admin.register(NotificationTemplate)
class NotificationTemplateAdmin(admin.ModelAdmin):
    list_display = [
        "template_code",
        "notification_type",
        "channel",
        "language_badge",
        "is_active",
        "updated_at",
    ]
    list_filter = [
        "language",
        "channel",
        "is_active",
        "notification_type",
    ]
    search_fields = [
        "template_code",
        "title_template",
        "body_template",
        "description",
    ]
    fieldsets = (
        (_("Identifier & Routing"), {
            "fields": ("template_code", "notification_type", "channel", "language", "is_active", "description")
        }),
        (_("Template Content"), {
            "fields": ("title_template", "body_template"),
            "description": _(
                "Supported placeholders: {name}, {otp_code}, {amount_rwf}, {transaction_ref}, "
                "{test_date}, {test_center}, {irembo_ref}, {score}, {max_score}, {expiry_minutes}"
            ),
        }),
    )

    @admin.display(description=_("Language"))
    def language_badge(self, obj):
        labels = {"rw": "Kinyarwanda", "en": "English", "fr": "French"}
        return labels.get(obj.language, obj.language.upper())


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "sms_enabled",
        "in_app_enabled",
        "email_enabled",
        "preferred_language",
        "updated_at",
    ]
    list_filter = [
        "preferred_language",
        "sms_enabled",
        "in_app_enabled",
        "email_enabled",
        "exam_alerts",
        "booking_alerts",
    ]
    search_fields = [
        "user__phone_number",
        "user__first_name",
        "user__last_name",
        "user__email",
    ]
