from rest_framework import serializers

from apps.live_classes.models import AttendanceStatus, ClassAttendance


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
