from rest_framework import serializers

from apps.accounts.models import User
from apps.live_classes.models import Cohort, LiveClass, LiveClassSchedule
from apps.live_classes.serializers.cohort_serializers import (
    CohortListSerializer,
    UserBriefSerializer,
)
from apps.live_classes.serializers.resource_serializers import ClassResourceSerializer


class LiveClassListSerializer(serializers.ModelSerializer):
    """Summary view of live classes for calendars and timetables."""
    tutor_name = serializers.CharField(source="tutor.get_full_name", read_only=True)
    cohort_name = serializers.CharField(source="cohort.name", read_only=True)
    cohort_code = serializers.CharField(source="cohort.code", read_only=True)
    module_title = serializers.CharField(source="module.title", read_only=True)
    lesson_title = serializers.CharField(source="lesson.title", read_only=True)
    created_by_name = serializers.CharField(source="created_by.get_full_name", read_only=True)
    created_by_role = serializers.CharField(source="created_by.role", read_only=True)
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
            "created_by",
            "created_by_name",
            "created_by_role",
            "scheduled_date",
            "start_time",
            "end_time",
            "google_meet_url",
            "status",
            "is_published",
            "is_past",
            "recording_url",
            "schedule",
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
    created_by_name = serializers.CharField(source="created_by.get_full_name", read_only=True)
    created_by_role = serializers.CharField(source="created_by.role", read_only=True)
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
            "created_by",
            "created_by_name",
            "created_by_role",
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
            "status",
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


class LiveClassRecurringScheduleSerializer(serializers.Serializer):
    """Payload for scheduling recurring live classes for given days and period."""

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
    day_of_week = serializers.IntegerField(min_value=0, max_value=6, required=False, allow_null=True, default=None)
    days_of_week = serializers.ListField(
        child=serializers.IntegerField(min_value=0, max_value=6),
        required=False,
        default=list,
    )
    start_time = serializers.TimeField()
    end_time = serializers.TimeField()
    start_date = serializers.DateField()
    end_date = serializers.DateField(required=False, allow_null=True, default=None)
    period_months = serializers.IntegerField(min_value=1, max_value=12, required=False, default=3)
    period_unit = serializers.ChoiceField(choices=["months", "years"], required=False, default="months")
    google_meet_url = serializers.CharField(required=False, allow_blank=True, default="")
    is_published = serializers.BooleanField(default=True)
    notes = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        if attrs["start_time"] >= attrs["end_time"]:
            raise serializers.ValidationError({"end_time": "Start time must be strictly before end time."})

        # Consolidate days_of_week
        days = list(attrs.get("days_of_week") or [])
        single_day = attrs.get("day_of_week")
        if single_day is not None and single_day not in days:
            days.append(single_day)

        if not days:
            raise serializers.ValidationError({"days_of_week": "At least one day of the week must be selected."})

        attrs["days_of_week"] = sorted(list(set(days)))

        if attrs.get("end_date") and attrs["end_date"] < attrs["start_date"]:
            raise serializers.ValidationError({"end_date": "End date must be greater than or equal to start date."})

        return attrs


class LiveClassScheduleSerializer(serializers.ModelSerializer):
    """Serializer for master class schedules."""

    cohort_name = serializers.CharField(source="cohort.name", read_only=True)
    cohort_code = serializers.CharField(source="cohort.code", read_only=True)
    tutor_name = serializers.CharField(source="tutor.get_full_name", read_only=True)
    created_by_name = serializers.CharField(source="created_by.get_full_name", read_only=True)
    created_by_role = serializers.CharField(source="created_by.role", read_only=True)
    total_sessions_count = serializers.IntegerField(read_only=True)
    next_session_date = serializers.SerializerMethodField()
    next_upcoming_session = serializers.SerializerMethodField()

    class Meta:
        model = LiveClassSchedule
        fields = [
            "id",
            "title",
            "topic",
            "cohort",
            "cohort_name",
            "cohort_code",
            "tutor",
            "tutor_name",
            "schedule_mode",
            "days_of_week",
            "start_time",
            "end_time",
            "start_date",
            "end_date",
            "period_months",
            "period_unit",
            "google_meet_url",
            "is_published",
            "notes",
            "is_active",
            "total_sessions_count",
            "next_session_date",
            "next_upcoming_session",
            "created_by",
            "created_by_name",
            "created_by_role",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_next_session_date(self, obj):
        nxt = obj.next_upcoming_session
        return str(nxt.scheduled_date) if nxt else None

    def get_next_upcoming_session(self, obj):
        nxt = obj.next_upcoming_session
        if not nxt:
            return None
        return {
            "id": str(nxt.id),
            "title": nxt.title,
            "scheduled_date": str(nxt.scheduled_date),
            "start_time": str(nxt.start_time),
            "end_time": str(nxt.end_time),
            "google_meet_url": nxt.google_meet_url,
            "status": nxt.status,
        }


class LiveClassScheduleUpdateSerializer(serializers.Serializer):
    """Payload for updating master schedule and its child sessions."""

    title = serializers.CharField(max_length=200, required=False)
    topic = serializers.CharField(max_length=300, required=False, allow_blank=True)
    cohort = serializers.PrimaryKeyRelatedField(
        queryset=Cohort.objects.all(), required=False, allow_null=True
    )
    tutor = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), required=False, allow_null=True
    )
    start_time = serializers.TimeField(required=False)
    end_time = serializers.TimeField(required=False)
    google_meet_url = serializers.CharField(required=False, allow_blank=True)
    is_published = serializers.BooleanField(required=False)
    notes = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        if "start_time" in attrs and "end_time" in attrs:
            if attrs["start_time"] >= attrs["end_time"]:
                raise serializers.ValidationError({"end_time": "Start time must be strictly before end time."})
        return attrs
