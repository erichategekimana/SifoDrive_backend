"""
apps/live_classes/admin.py
==========================
Enterprise Django Admin interface for Live Classes, Cohorts, and Attendance.
"""

from django.contrib import admin
from django.utils.html import format_html

from .models import (
    AttendanceStatus,
    ClassAttendance,
    ClassResource,
    Cohort,
    LiveClass,
    LiveClassStatus,
)


class ClassAttendanceInline(admin.TabularInline):
    model = ClassAttendance
    extra = 0
    fields = ["student", "status", "minutes_attended", "joined_at", "marked_by", "notes"]
    autocomplete_fields = ["student", "marked_by"]
    show_change_link = True


class ClassResourceInline(admin.TabularInline):
    model = ClassResource
    extra = 0
    fields = ["title", "file", "external_link", "description", "uploaded_by"]
    autocomplete_fields = ["uploaded_by"]
    show_change_link = True


@admin.register(Cohort)
class CohortAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "code",
        "start_date",
        "end_date",
        "max_capacity",
        "get_student_count",
        "get_tutor_count",
        "is_active",
    ]
    list_filter = ["is_active", "start_date"]
    search_fields = ["name", "code", "description", "schedule_description"]
    filter_horizontal = ["assigned_tutors", "students"]
    ordering = ["-start_date", "name"]

    @admin.display(description="Enrolled Students")
    def get_student_count(self, obj):
        return obj.students.count()

    @admin.display(description="Assigned Tutors")
    def get_tutor_count(self, obj):
        return obj.assigned_tutors.count()


@admin.register(LiveClass)
class LiveClassAdmin(admin.ModelAdmin):
    list_display = [
        "title",
        "scheduled_date",
        "start_time",
        "end_time",
        "tutor",
        "cohort",
        "status_badge",
        "is_published",
        "google_meet_link",
    ]
    list_filter = ["status", "is_published", "scheduled_date", "cohort"]
    search_fields = [
        "title",
        "topic",
        "notes",
        "tutor__phone_number",
        "tutor__first_name",
        "tutor__last_name",
        "cohort__name",
        "cohort__code",
    ]
    autocomplete_fields = ["tutor", "created_by"]
    inlines = [ClassResourceInline, ClassAttendanceInline]
    ordering = ["-scheduled_date", "start_time"]
    date_hierarchy = "scheduled_date"

    @admin.display(description="Status")
    def status_badge(self, obj):
        colors = {
            LiveClassStatus.SCHEDULED: "#2563eb",
            LiveClassStatus.IN_PROGRESS: "#16a34a",
            LiveClassStatus.COMPLETED: "#4b5563",
            LiveClassStatus.RESCHEDULED: "#d97706",
            LiveClassStatus.CANCELLED: "#dc2626",
        }
        color = colors.get(obj.status, "#6b7280")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; border-radius: 4px; font-weight: 500;">{}</span>',
            color,
            obj.get_status_display(),
        )

    @admin.display(description="Meet Link")
    def google_meet_link(self, obj):
        if obj.google_meet_url:
            return format_html(
                '<a href="{}" target="_blank" rel="noopener noreferrer" style="color: #2563eb;">Open Meet ↗</a>',
                obj.google_meet_url,
            )
        return "—"


@admin.register(ClassAttendance)
class ClassAttendanceAdmin(admin.ModelAdmin):
    list_display = [
        "student",
        "live_class",
        "status_badge",
        "minutes_attended",
        "joined_at",
        "marked_by",
        "created_at",
    ]
    list_filter = ["status", "live_class__scheduled_date", "live_class__cohort"]
    search_fields = [
        "student__phone_number",
        "student__first_name",
        "student__last_name",
        "live_class__title",
        "notes",
    ]
    autocomplete_fields = ["student", "marked_by"]
    ordering = ["-created_at"]

    @admin.display(description="Status")
    def status_badge(self, obj):
        colors = {
            AttendanceStatus.PRESENT: "#16a34a",
            AttendanceStatus.LATE: "#d97706",
            AttendanceStatus.ABSENT: "#dc2626",
            AttendanceStatus.EXCUSED: "#6b7280",
            AttendanceStatus.WATCHED_RECORDING: "#2563eb",
        }
        color = colors.get(obj.status, "#6b7280")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 6px; border-radius: 4px; font-size: 11px;">{}</span>',
            color,
            obj.get_status_display(),
        )


@admin.register(ClassResource)
class ClassResourceAdmin(admin.ModelAdmin):
    list_display = ["title", "live_class", "uploaded_by", "created_at"]
    search_fields = ["title", "description", "live_class__title"]
    autocomplete_fields = ["live_class", "uploaded_by"]
    ordering = ["-created_at"]
