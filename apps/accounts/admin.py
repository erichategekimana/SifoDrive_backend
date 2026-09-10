"""
apps/accounts/admin.py
=======================
Django Admin configuration for User management.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import OTPVerification, StudentProfile, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Custom admin for the Sifo Drive User model."""

    list_display = [
        "phone_number", "full_name", "role", "status",
        "student_id", "is_verified", "created_at",
    ]
    list_filter = ["role", "status", "is_staff", "created_at"]
    search_fields = ["phone_number", "first_name", "last_name", "email", "student_id"]
    ordering = ["-created_at"]
    readonly_fields = [
        "id", "student_id", "created_at", "updated_at",
        "last_login", "privacy_policy_accepted_at",
    ]

    fieldsets = (
        (_("Identity"), {
            "fields": ("id", "phone_number", "email", "first_name", "last_name"),
        }),
        (_("Role & Status"), {
            "fields": ("role", "status", "student_id", "assigned_tutor"),
        }),
        (_("Enterprise"), {
            "fields": ("school_name", "station_quota"),
            "classes": ("collapse",),
        }),
        (_("Compliance & Consent"), {
            "fields": (
                "terms_of_service_accepted",
                "terms_of_service_accepted_at",
                "privacy_policy_accepted",
                "privacy_policy_accepted_at",
            ),
            "classes": ("collapse",),
        }),
        (_("Django Auth"), {
            "fields": ("password", "is_active", "is_staff", "is_superuser", "groups", "user_permissions"),
            "classes": ("collapse",),
        }),
        (_("Timestamps"), {
            "fields": ("created_at", "updated_at", "last_login", "last_login_ip"),
            "classes": ("collapse",),
        }),
    )

    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": (
                "phone_number", "first_name", "last_name",
                "role", "password1", "password2",
            ),
        }),
    )

    # IMPORTANT: Never expose national_id_encrypted in admin — audit log only
    def get_exclude(self, request, obj=None):
        return ["national_id_encrypted"]


@admin.register(OTPVerification)
class OTPVerificationAdmin(admin.ModelAdmin):
    list_display = ["phone_number", "purpose", "is_used", "is_expired", "expires_at", "attempt_count"]
    list_filter = ["purpose", "is_used"]
    search_fields = ["phone_number"]
    readonly_fields = ["id", "otp_hash", "created_at"]

    def get_queryset(self, request):
        return super().get_queryset(request).order_by("-created_at")


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "license_category", "preferred_language", "enrollment_date", "current_streak_days"]
    search_fields = ["user__phone_number", "user__student_id"]
    readonly_fields = ["user", "enrollment_date"]
