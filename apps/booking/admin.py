"""
apps/booking/admin.py
=====================
Django Admin configuration for Driving Test Booking applications, category fees,
and partner driving instructors.
"""

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from apps.booking.models import (
    BookingApplication,
    BookingState,
    CategoryPrice,
    PartnerTeacher,
)


@admin.register(CategoryPrice)
class CategoryPriceAdmin(admin.ModelAdmin):
    list_display = ["category", "formatted_price", "description", "is_active", "updated_at"]
    list_filter = ["is_active", "category"]
    search_fields = ["category", "description"]
    list_editable = ["is_active"]

    @admin.display(description=_("Price (RWF)"))
    def formatted_price(self, obj):
        return f"{obj.price_rwf:,} RWF"


@admin.register(PartnerTeacher)
class PartnerTeacherAdmin(admin.ModelAdmin):
    list_display = [
        "full_name",
        "phone_number",
        "driving_school_affiliation",
        "is_active",
        "students_referred_count",
        "updated_at",
    ]
    list_filter = ["is_active", "driving_school_affiliation"]
    search_fields = ["first_name", "last_name", "phone_number", "driving_school_affiliation"]
    list_editable = ["is_active"]

    @admin.display(description=_("Referred Bookings"))
    def students_referred_count(self, obj):
        return obj.student_bookings.count()


@admin.register(BookingApplication)
class BookingApplicationAdmin(admin.ModelAdmin):
    list_display = [
        "ticket_number",
        "full_name",
        "phone_number",
        "license_category",
        "preferred_district",
        "working_site",
        "partner_teacher",
        "formatted_price",
        "state_badge",
        "irembo_billing_number",
        "submitted_at",
    ]
    list_filter = [
        "state",
        "license_category",
        "preferred_district",
        "partner_teacher",
        "submitted_at",
    ]
    search_fields = [
        "ticket_number",
        "first_name",
        "last_name",
        "phone_number",
        "irembo_billing_number",
        "irembo_application_number",
    ]
    readonly_fields = [
        "id",
        "ticket_number",
        "applicant",
        "national_id_hash",
        "price_rwf",
        "submitted_at",
        "completed_at",
        "created_at",
        "updated_at",
    ]
    fieldsets = (
        (_("Application Identifier & Applicant"), {
            "fields": ("ticket_number", "applicant", "first_name", "last_name", "phone_number", "date_of_birth")
        }),
        (_("Test Specifications"), {
            "fields": ("license_category", "preferred_district", "working_site", "partner_teacher", "price_rwf")
        }),
        (_("Workflow & Agent Assignment"), {
            "fields": ("state", "assigned_agent", "agent_notes")
        }),
        (_("Irembo Confirmation & Billing Details"), {
            "fields": (
                "irembo_billing_number",
                "irembo_application_number",
                "confirmed_test_date",
                "confirmed_test_time",
                "confirmed_venue",
                "confirmation_pdf",
                "completed_at",
            )
        }),
        (_("Security & Audit"), {
            "fields": ("id", "national_id_hash", "created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    @admin.display(description=_("Price"))
    def formatted_price(self, obj):
        return f"{obj.price_rwf:,} RWF"

    @admin.display(description=_("Status"))
    def state_badge(self, obj):
        colors = {
            BookingState.PENDING: "#ffc107",           # Amber
            BookingState.PROCESSING: "#0dcaf0",        # Cyan
            BookingState.COMPLETED: "#198754",         # Green
            BookingState.SLOTS_UNAVAILABLE: "#fd7e14", # Orange
            BookingState.CANCELLED: "#dc3545",         # Red
        }
        color = colors.get(obj.state, "#6c757d")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 7px; border-radius: 4px; font-weight: bold; font-size: 11px;">{}</span>',
            color,
            obj.state,
        )
