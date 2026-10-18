from rest_framework import serializers

from apps.live_classes.models import AttendanceStatus, ClassAttendance


class ClassAttendanceSerializer(serializers.ModelSerializer):
    """Individual student attendance record."""
    student_name = serializers.CharField(source="student.get_full_name", read_only=True)
    student_phone = serializers.CharField(source="student.phone_number", read_only=True)
    student_photo = serializers.SerializerMethodField(read_only=True)
    marked_by_name = serializers.CharField(source="marked_by.get_full_name", read_only=True)
    class_title = serializers.CharField(source="live_class.title", read_only=True)
    scheduled_at = serializers.DateTimeField(source="live_class.scheduled_at", read_only=True)

    class Meta:
        model = ClassAttendance
        fields = [
            "id",
            "live_class",
            "class_title",
            "scheduled_at",
            "student",
            "student_name",
            "student_phone",
            "student_photo",
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
            "class_title",
            "scheduled_at",
            "student_name",
            "student_phone",
            "marked_by",
            "marked_by_name",
            "created_at",
            "updated_at",
        ]

    def get_student_photo(self, obj):
        if obj.student.profile_photo:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.student.profile_photo.url)
            return obj.student.profile_photo.url
        return None

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # If viewed in student context, EXCUSED maps to PRESENT on their view
        # while tutors and admins can see that it was an excuse.
        if self.context.get("for_student") or (
            self.context.get("request") and getattr(self.context["request"].user, "role", None) == "STUDENT"
        ):
            if data.get("status") == AttendanceStatus.EXCUSED:
                data["status"] = AttendanceStatus.PRESENT
        return data


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
