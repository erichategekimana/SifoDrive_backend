"""
apps/live_classes/serializers.py
================================
REST API Serializers for Live Classes, Cohorts, Attendance Tracking, and Resources.
Supports role-based visibility and validation.
"""

from rest_framework import serializers

from apps.accounts.models import User
from apps.lms.models import Lesson, Module
from .models import (
    AttendanceStatus,
    ClassAttendance,
    ClassResource,
    Cohort,
    LiveClass,
    LiveClassStatus,
)


# ===========================================================================
# User Brief Serializers
# ===========================================================================

class UserBriefSerializer(serializers.ModelSerializer):
    """Compact user profile representation for tutors and students."""
    full_name = serializers.CharField(source="get_full_name", read_only=True)

    class Meta:
        model = User
        fields = ["id", "phone_number", "first_name", "last_name", "full_name", "role"]
        read_only_fields = fields


# ===========================================================================
# Cohort Serializers
# ===========================================================================

class CohortListSerializer(serializers.ModelSerializer):
    """List serializer for Cohort / student batches."""
    assigned_tutors = UserBriefSerializer(many=True, read_only=True)
    student_count = serializers.IntegerField(read_only=True)
    tutor_count = serializers.IntegerField(read_only=True)
    ongoing_student_count = serializers.SerializerMethodField()

    def get_ongoing_student_count(self, obj) -> int:
        from .services import CohortService
        return CohortService.get_ongoing_students_count(obj)

    class Meta:
        model = Cohort
        fields = [
            "id",
            "name",
            "code",
            "description",
            "start_date",
            "end_date",
            "max_capacity",
            "is_active",
            "schedule_description",
            "assigned_tutors",
            "student_count",
            "tutor_count",
            "ongoing_student_count",
            "created_at",
        ]
        read_only_fields = ["id", "assigned_tutors", "student_count", "tutor_count", "ongoing_student_count", "created_at"]


class CohortDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer with assigned tutors and student roster summary."""
    assigned_tutors = UserBriefSerializer(many=True, read_only=True)
    student_count = serializers.IntegerField(read_only=True)
    tutor_count = serializers.IntegerField(read_only=True)
    ongoing_student_count = serializers.SerializerMethodField()

    def get_ongoing_student_count(self, obj) -> int:
        from .services import CohortService
        return CohortService.get_ongoing_students_count(obj)

    class Meta:
        model = Cohort
        fields = [
            "id",
            "name",
            "code",
            "description",
            "start_date",
            "end_date",
            "max_capacity",
            "is_active",
            "schedule_description",
            "assigned_tutors",
            "student_count",
            "tutor_count",
            "ongoing_student_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "assigned_tutors", "student_count", "tutor_count", "ongoing_student_count", "created_at", "updated_at"]


class CohortCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for System Admin and Training Admin to create or modify cohorts."""
    code = serializers.CharField(max_length=50, required=False, allow_blank=True)
    description = serializers.CharField(max_length=165, required=False, allow_blank=True)
    end_date = serializers.DateField(required=True)

    class Meta:
        model = Cohort
        fields = [
            "name",
            "code",
            "description",
            "start_date",
            "end_date",
            "max_capacity",
            "schedule_description",
            "is_active",
        ]

    def validate(self, attrs):
        start = attrs.get("start_date") or (self.instance.start_date if self.instance else None)
        end = attrs.get("end_date") or (self.instance.end_date if self.instance else None)
        if start and end and end < start:
            raise serializers.ValidationError({"end_date": "End date cannot precede start date."})

        desc = attrs.get("description", "")
        if desc and len(desc) > 165:
            raise serializers.ValidationError({"description": "Description cannot exceed 165 characters."})

        # Cohort can be deactivated ONLY when all students have completed or withdrawn from the course
        if "is_active" in attrs and self.instance and self.instance.is_active and not attrs["is_active"]:
            from .services import CohortService
            can_deactivate, ongoing = CohortService.can_deactivate_cohort(self.instance)
            if not can_deactivate:
                raise serializers.ValidationError({
                    "is_active": f"Cannot deactivate cohort '{self.instance.name}'. There are {ongoing} active student(s) currently enrolled who have not completed or withdrawn from the course."
                })

        if not attrs.get("code") and not (self.instance and self.instance.code):
            import uuid
            from django.utils import timezone
            name_slug = attrs.get("name", "COHORT").strip().upper().replace(" ", "-")[:12]
            attrs["code"] = f"{name_slug}-{timezone.now().strftime('%y%m')}-{uuid.uuid4().hex[:4].upper()}"

        return attrs


class CohortAssignStudentsSerializer(serializers.Serializer):
    """Payload for bulk enrolling or unenrolling students in a cohort."""
    student_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=False,
        help_text="List of student User UUIDs to assign or remove",
    )


class CohortAssignTutorsSerializer(serializers.Serializer):
    """Payload for assigning or removing tutors in a cohort."""
    tutor_ids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=False,
        help_text="List of tutor User UUIDs to assign or remove",
    )


# ===========================================================================
# Class Resource Serializers
# ===========================================================================

class ClassResourceSerializer(serializers.ModelSerializer):
    """Serializer for supplementary study materials attached to a class."""
    uploaded_by_name = serializers.CharField(source="uploaded_by.get_full_name", read_only=True)

    class Meta:
        model = ClassResource
        fields = [
            "id",
            "live_class",
            "title",
            "file",
            "external_link",
            "description",
            "uploaded_by",
            "uploaded_by_name",
            "created_at",
        ]
        read_only_fields = ["id", "uploaded_by", "uploaded_by_name", "created_at"]


class ClassResourceCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClassResource
        fields = [
            "title",
            "file",
            "external_link",
            "description",
        ]

    def validate(self, attrs):
        if not attrs.get("file") and not attrs.get("external_link"):
            raise serializers.ValidationError("Either an uploaded file or an external link must be provided.")
        return attrs


# ===========================================================================
# Live Class Serializers
# ===========================================================================

class LiveClassListSerializer(serializers.ModelSerializer):
    """Summary view of live classes for calendars and timetables."""
    tutor_name = serializers.CharField(source="tutor.get_full_name", read_only=True)
    cohort_name = serializers.CharField(source="cohort.name", read_only=True)
    cohort_code = serializers.CharField(source="cohort.code", read_only=True)
    module_title = serializers.CharField(source="module.title", read_only=True)
    lesson_title = serializers.CharField(source="lesson.title", read_only=True)
    is_past = serializers.BooleanField(read_only=True)

    class Meta:
        model = LiveClass
        fields = [
            "id",
            "title",
            "topic",
            "cohort",
            "cohort_name",
            "cohort_code",
            "tutor",
            "tutor_name",
            "module",
            "module_title",
            "lesson",
            "lesson_title",
            "scheduled_date",
            "start_time",
            "end_time",
            "google_meet_url",
            "status",
            "is_published",
            "is_past",
            "recording_url",
            "created_at",
        ]
        read_only_fields = fields


class LiveClassDetailSerializer(serializers.ModelSerializer):
    """Detailed view including curriculum link, notes, and attached resources."""
    tutor = UserBriefSerializer(read_only=True)
    cohort = CohortListSerializer(read_only=True)
    resources = ClassResourceSerializer(many=True, read_only=True)
    module_title = serializers.CharField(source="module.title", read_only=True)
    lesson_title = serializers.CharField(source="lesson.title", read_only=True)
    is_past = serializers.BooleanField(read_only=True)

    class Meta:
        model = LiveClass
        fields = [
            "id",
            "title",
            "topic",
            "cohort",
            "tutor",
            "module",
            "module_title",
            "lesson",
            "lesson_title",
            "scheduled_date",
            "start_time",
            "end_time",
            "google_meet_url",
            "status",
            "is_published",
            "is_past",
            "notes",
            "recording_url",
            "actual_started_at",
            "actual_ended_at",
            "resources",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class LiveClassCreateUpdateSerializer(serializers.ModelSerializer):
    """Admin and Training Admin serializer to schedule or edit live classes."""

    class Meta:
        model = LiveClass
        fields = [
            "title",
            "topic",
            "cohort",
            "tutor",
            "module",
            "lesson",
            "scheduled_date",
            "start_time",
            "end_time",
            "google_meet_url",
            "notes",
            "is_published",
            "recording_url",
        ]

    def validate(self, attrs):
        start = attrs.get("start_time") or (self.instance.start_time if self.instance else None)
        end = attrs.get("end_time") or (self.instance.end_time if self.instance else None)
        if start and end and start >= end:
            raise serializers.ValidationError({"end_time": "Start time must be strictly before end time."})

        meet_url = attrs.get("google_meet_url") or (self.instance.google_meet_url if self.instance else "")
        if meet_url and not ("meet.google.com" in meet_url or meet_url.startswith("http")):
            raise serializers.ValidationError({"google_meet_url": "Please provide a valid meeting URL."})

        return attrs


class LiveClassRescheduleSerializer(serializers.Serializer):
    """Payload for rescheduling a live session."""
    scheduled_date = serializers.DateField(required=True)
    start_time = serializers.TimeField(required=True)
    end_time = serializers.TimeField(required=True)
    reason = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        if attrs["start_time"] >= attrs["end_time"]:
            raise serializers.ValidationError({"end_time": "Start time must be before end time."})
        return attrs


class LiveClassEndSessionSerializer(serializers.Serializer):
    """Payload for completing a session and attaching the recording."""
    recording_url = serializers.URLField(required=False, allow_blank=True, default="")


# ===========================================================================
# Attendance Serializers
# ===========================================================================

class ClassAttendanceSerializer(serializers.ModelSerializer):
    """Individual student attendance record."""
    student_name = serializers.CharField(source="student.get_full_name", read_only=True)
    student_phone = serializers.CharField(source="student.phone_number", read_only=True)
    marked_by_name = serializers.CharField(source="marked_by.get_full_name", read_only=True)

    class Meta:
        model = ClassAttendance
        fields = [
            "id",
            "live_class",
            "student",
            "student_name",
            "student_phone",
            "status",
            "joined_at",
            "minutes_attended",
            "marked_by",
            "marked_by_name",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "student_name",
            "student_phone",
            "marked_by",
            "marked_by_name",
            "created_at",
            "updated_at",
        ]


class BatchAttendanceItemSerializer(serializers.Serializer):
    """Item structure for batch recording attendance."""
    student_id = serializers.UUIDField(required=True)
    status = serializers.ChoiceField(choices=AttendanceStatus.choices, default=AttendanceStatus.PRESENT)
    minutes_attended = serializers.IntegerField(min_value=0, default=0, required=False)
    joined_at = serializers.DateTimeField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class BatchAttendanceRecordSerializer(serializers.Serializer):
    """Root payload for tutor batch attendance recording."""
    records = serializers.ListField(
        child=BatchAttendanceItemSerializer(),
        allow_empty=False,
    )


class StudentAttendanceSummarySerializer(serializers.Serializer):
    """Attendance rate and exam readiness report."""
    rate = serializers.FloatField()
    percentage = serializers.FloatField()
    is_eligible_for_exam = serializers.BooleanField()
    threshold_required_percentage = serializers.FloatField()
    present_count = serializers.IntegerField()
    late_count = serializers.IntegerField()
    absent_count = serializers.IntegerField()
    excused_count = serializers.IntegerField()
    watched_recording_count = serializers.IntegerField()
    total_attended = serializers.IntegerField()


class LiveClassRecurringScheduleSerializer(serializers.Serializer):
    """Payload for scheduling recurring live classes for a given day and period (months)."""

    title = serializers.CharField(max_length=200)
    topic = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")
    cohort = serializers.PrimaryKeyRelatedField(
        queryset=Cohort.objects.all(),
        required=False,
        allow_null=True,
        default=None,
    )
    tutor = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        required=False,
        allow_null=True,
        default=None,
    )
    day_of_week = serializers.IntegerField(min_value=0, max_value=6)  # 0=Monday ... 6=Sunday
    start_time = serializers.TimeField()
    end_time = serializers.TimeField()
    start_date = serializers.DateField()
    period_months = serializers.IntegerField(min_value=1, max_value=12, default=3)
    google_meet_url = serializers.CharField(required=False, allow_blank=True, default="")
    is_published = serializers.BooleanField(default=True)
    notes = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        if attrs["start_time"] >= attrs["end_time"]:
            raise serializers.ValidationError({"end_time": "Start time must be strictly before end time."})
        return attrs

