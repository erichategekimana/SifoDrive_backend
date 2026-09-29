from rest_framework import serializers

from apps.accounts.models import User
from apps.live_classes.models import Cohort


class UserBriefSerializer(serializers.ModelSerializer):
    """Compact user profile representation for tutors and students."""
    full_name = serializers.CharField(source="get_full_name", read_only=True)

    class Meta:
        model = User
        fields = ["id", "phone_number", "first_name", "last_name", "full_name", "role"]
        read_only_fields = fields


class CohortListSerializer(serializers.ModelSerializer):
    """List serializer for Cohort / student batches."""
    assigned_tutors = UserBriefSerializer(many=True, read_only=True)
    student_count = serializers.IntegerField(read_only=True)
    tutor_count = serializers.IntegerField(read_only=True)
    ongoing_student_count = serializers.SerializerMethodField()

    def get_ongoing_student_count(self, obj) -> int:
        from apps.live_classes.services import CohortService
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
        from apps.live_classes.services import CohortService
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
            from apps.live_classes.services import CohortService
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
