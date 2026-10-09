from rest_framework import serializers
from apps.lms.models import HelpTicket, TicketCategory, TicketPriority, TicketRecipientRole, TicketStatus


class HelpTicketSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.full_name", read_only=True)
    user_phone = serializers.CharField(source="user.phone_number", read_only=True)
    user_role = serializers.CharField(source="user.role", read_only=True)
    assigned_to_name = serializers.CharField(source="assigned_to.full_name", read_only=True, allow_null=True)

    class Meta:
        model = HelpTicket
        fields = [
            "id",
            "user",
            "user_name",
            "user_phone",
            "user_role",
            "recipient_role",
            "category",
            "subject",
            "message",
            "priority",
            "status",
            "assigned_to",
            "assigned_to_name",
            "response",
            "resolved_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "user",
            "user_name",
            "user_phone",
            "user_role",
            "status",
            "assigned_to",
            "assigned_to_name",
            "response",
            "resolved_at",
            "created_at",
            "updated_at",
        ]


class HelpTicketCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = HelpTicket
        fields = [
            "recipient_role",
            "category",
            "subject",
            "message",
            "priority",
        ]


class HelpTicketResolveSerializer(serializers.Serializer):
    response = serializers.CharField(required=True)
    status = serializers.ChoiceField(
        choices=[TicketStatus.RESOLVED, TicketStatus.CLOSED],
        default=TicketStatus.RESOLVED,
    )


class AnnouncementSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()
    author_role = serializers.CharField(source="author.role", read_only=True)
    date = serializers.SerializerMethodField()
    course_name = serializers.CharField(source="course.title", read_only=True, allow_null=True)
    course_title = serializers.CharField(source="course.title", read_only=True, allow_null=True)
    cohort_name = serializers.CharField(source="cohort.name", read_only=True, allow_null=True)
    cohort_names = serializers.SerializerMethodField()
    target_url = serializers.SerializerMethodField()

    class Meta:
        from apps.lms.models import Announcement
        model = Announcement
        fields = [
            "id",
            "title",
            "content",
            "author",
            "author_name",
            "author_role",
            "date",
            "created_at",
            "category",
            "is_pinned",
            "course",
            "course_name",
            "course_title",
            "target_type",
            "cohort",
            "cohort_name",
            "cohort_names",
            "target_url",
        ]

    def get_author_name(self, obj) -> str:
        if not obj.author:
            return "Instructor"
        full = f"{obj.author.first_name} {obj.author.last_name}".strip()
        return full or obj.author.phone_number or "Instructor"

    def get_date(self, obj) -> str:
        return obj.created_at.strftime("%Y-%m-%d") if obj.created_at else ""

    def get_cohort_names(self, obj) -> list:
        return [c.name for c in obj.cohorts.all()]

    def get_target_url(self, obj) -> str:
        if obj.course_id:
            return f"/courses/{obj.course_id}?announcement={obj.id}"
        return f"/courses?announcement={obj.id}"


class AnnouncementCreateSerializer(serializers.Serializer):
    course_id = serializers.UUIDField(required=False, allow_null=True)
    title = serializers.CharField(max_length=255, required=True)
    content = serializers.CharField(required=True)
    category = serializers.CharField(max_length=50, default="COURSE", required=False)
    is_pinned = serializers.BooleanField(default=False, required=False)
    target_type = serializers.CharField(max_length=30, default="ALL_ASSIGNED_COHORTS", required=False)
    cohort_id = serializers.UUIDField(required=False, allow_null=True)

    def validate(self, attrs):
        from apps.lms.models import AnnouncementTargetType
        from apps.live_classes.models import Cohort

        target_type = attrs.get("target_type", AnnouncementTargetType.ALL_ASSIGNED_COHORTS)
        cohort_id = attrs.get("cohort_id")
        request = self.context.get("request")
        user = request.user if request else None

        if target_type == AnnouncementTargetType.SINGLE_COHORT:
            if not cohort_id:
                raise serializers.ValidationError({"cohort_id": "Cohort ID is required when targeting a single cohort."})
            cohort = Cohort.objects.filter(id=cohort_id, is_deleted=False).first()
            if not cohort:
                raise serializers.ValidationError({"cohort_id": "Specified cohort does not exist."})
            if user and user.role == "TUTOR" and not cohort.assigned_tutors.filter(id=user.id).exists():
                raise serializers.ValidationError({"cohort_id": "You can only post announcements to cohorts assigned to you."})
            attrs["cohort_obj"] = cohort
        elif target_type == AnnouncementTargetType.ALL_ASSIGNED_COHORTS:
            if user and user.role == "TUTOR":
                assigned = user.assigned_cohorts.filter(is_deleted=False)
                if not assigned.exists():
                    raise serializers.ValidationError({"target_type": "You do not have any assigned cohorts to broadcast to."})
                attrs["cohorts_objs"] = list(assigned)
        return attrs

    def create(self, validated_data):
        from apps.lms.models import Announcement, AnnouncementTargetType, Course

        cohort_obj = validated_data.pop("cohort_obj", None)
        cohorts_objs = validated_data.pop("cohorts_objs", None)
        course_id = validated_data.pop("course_id", None)
        validated_data.pop("cohort_id", None)

        course = None
        if course_id:
            course = Course.objects.filter(id=course_id, is_deleted=False).first()

        request = self.context.get("request")
        author = request.user

        announcement = Announcement.objects.create(
            author=author,
            course=course,
            cohort=cohort_obj,
            **validated_data
        )

        target_type = validated_data.get("target_type")
        if target_type == AnnouncementTargetType.SINGLE_COHORT and cohort_obj:
            announcement.cohorts.set([cohort_obj])
        elif target_type == AnnouncementTargetType.ALL_ASSIGNED_COHORTS and cohorts_objs:
            announcement.cohorts.set(cohorts_objs)
        elif target_type == AnnouncementTargetType.ALL_ASSIGNED_COHORTS and author and author.assigned_cohorts.exists():
            announcement.cohorts.set(author.assigned_cohorts.filter(is_deleted=False))

        return announcement
