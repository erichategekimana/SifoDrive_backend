"""
apps/accounts/admin.py
=======================
Django Admin configuration for User management.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import (
    AgentCommission,
    AgentProfile,
    EnterpriseProfile,
    OTPVerification,
    ReviewerProfile,
    ServiceCommissionConfig,
    StudentProfile,
    TutorProfile,
    User,
)


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
            "fields": ("role", "status", "student_id", "assigned_tutor", "created_by_agent"),
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

    def get_exclude(self, request, obj=None):
        return ["national_id_encrypted"]


@admin.register(OTPVerification)
class OTPVerificationAdmin(admin.ModelAdmin):
    list_display = ["phone_number", "purpose", "is_used", "is_expired", "expires_at", "attempt_count"]
    list_filter = ["purpose", "is_used"]
    search_fields = ["phone_number"]
    readonly_fields = ["id", "otp_hash", "created_at"]


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "license_category", "preferred_language", "enrollment_date", "current_streak_days"]
    search_fields = ["user__phone_number", "user__student_id"]
    readonly_fields = ["user", "enrollment_date"]


@admin.register(TutorProfile)
class TutorProfileAdmin(admin.ModelAdmin):
    list_display = ["tutor_code", "user", "title", "is_available_for_tutoring", "max_student_capacity", "rating"]
    search_fields = ["tutor_code", "user__first_name", "user__last_name", "user__phone_number"]
    list_filter = ["is_available_for_tutoring"]


@admin.register(EnterpriseProfile)
class EnterpriseProfileAdmin(admin.ModelAdmin):
    list_display = ["school_name", "registration_number", "district", "concurrent_station_quota", "is_verified_school"]
    search_fields = ["school_name", "registration_number", "district", "user__phone_number"]
    list_filter = ["is_verified_school", "district"]


@admin.register(ReviewerProfile)
class ReviewerProfileAdmin(admin.ModelAdmin):
    list_display = ["reviewer_code", "user", "inspector_badge_number", "total_reviews_completed", "is_active_reviewer"]
    search_fields = ["reviewer_code", "user__first_name", "user__last_name", "inspector_badge_number"]
    list_filter = ["is_active_reviewer"]


@admin.register(AgentProfile)
class AgentProfileAdmin(admin.ModelAdmin):
    list_display = ["agent_code", "business_name", "district", "sector", "total_accrued_rwf", "total_paid_out_rwf", "is_approved"]
    search_fields = ["agent_code", "business_name", "user__phone_number"]
    list_filter = ["is_approved", "district"]


@admin.register(ServiceCommissionConfig)
class ServiceCommissionConfigAdmin(admin.ModelAdmin):
    list_display = ["service_type", "service_name", "default_client_price_rwf", "commission_fee_rwf", "is_active"]
    list_filter = ["is_active"]


@admin.register(AgentCommission)
class AgentCommissionAdmin(admin.ModelAdmin):
    list_display = ["id", "agent", "service_type", "commission_amount_rwf", "status", "created_at"]
    search_fields = ["agent__agent_code", "client__phone_number", "client_phone_number"]
    list_filter = ["status", "service_type"]
