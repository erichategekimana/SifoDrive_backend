"""
apps/lms/serializers/group_serializers.py
=========================================
Serializers for course participant roster, study groups, and group chat.
"""

import hashlib
from rest_framework import serializers
from django.utils import timezone
from apps.accounts.models import User
from apps.lms.models import CourseGroup, CourseGroupMessage


AVATAR_PALETTE = [
    "#0055A5", "#058728", "#D97706", "#7C3AED", "#DB2777",
    "#2563EB", "#0D9488", "#4F46E5", "#DC2626", "#0284C7"
]


def get_avatar_color(identifier: str) -> str:
    """Generate consistent color from user ID/name."""
    h = int(hashlib.md5(identifier.encode("utf-8")).hexdigest(), 16)
    return AVATAR_PALETTE[h % len(AVATAR_PALETTE)]


def format_relative_time(dt) -> str:
    """Format datetime into a clean human relative string."""
    if not dt:
        return "Offline"
    now = timezone.now()
    diff = now - dt
    seconds = int(diff.total_seconds())

    if seconds < 120:
        return "Active now"
    if seconds < 3600:
        mins = max(1, seconds // 60)
        return f"{mins}m ago"
    if seconds < 86400:
        hours = max(1, seconds // 3600)
        return f"{hours}h ago"
    if seconds < 172800:
        return f"Yesterday at {dt.strftime('%H:%M')}"
    return dt.strftime("%b %d, %Y")


class CourseRosterUserSerializer(serializers.ModelSerializer):
    """Serializer for classmates & instructors on the course roster."""

    name = serializers.SerializerMethodField()
    role = serializers.SerializerMethodField()
    category = serializers.SerializerMethodField()
    avatar_color = serializers.SerializerMethodField()
    last_active = serializers.SerializerMethodField()
    profile_photo = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "name",
            "role",
            "student_id",
            "category",
            "avatar_color",
            "profile_photo",
            "last_active",
        ]

    def get_name(self, obj: User) -> str:
        name = f"{obj.first_name} {obj.last_name}".strip()
        return name if name else (obj.email or "Learner")

    def get_role(self, obj: User) -> str:
        return "Instructor" if obj.role == "TUTOR" else "Student"

    def get_category(self, obj: User) -> str:
        if obj.role == "TUTOR":
            return "Theory Lead Instructor"
        return "Course Participant"

    def get_avatar_color(self, obj: User) -> str:
        return get_avatar_color(str(obj.id))

    def get_last_active(self, obj: User) -> str:
        return format_relative_time(obj.last_login or obj.updated_at)

    def get_profile_photo(self, obj: User) -> str | None:
        if obj.profile_photo:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.profile_photo.url)
            return obj.profile_photo.url
        return None


class CourseGroupMessageSerializer(serializers.ModelSerializer):
    """Serializer for a single chat message in a group."""

    sender_name = serializers.SerializerMethodField()
    sender_role = serializers.SerializerMethodField()
    avatar_color = serializers.SerializerMethodField()
    profile_photo = serializers.SerializerMethodField()
    timestamp = serializers.SerializerMethodField()
    text = serializers.CharField(source="content")

    class Meta:
        model = CourseGroupMessage
        fields = [
            "id",
            "sender_id",
            "sender_name",
            "sender_role",
            "avatar_color",
            "profile_photo",
            "timestamp",
            "text",
            "created_at",
        ]

    def get_sender_name(self, obj: CourseGroupMessage) -> str:
        sender = obj.sender
        name = f"{sender.first_name} {sender.last_name}".strip()
        return name if name else (sender.email or "User")

    def get_sender_role(self, obj: CourseGroupMessage) -> str:
        return "Tutor" if obj.sender.role in ["TUTOR", "SYSTEM_ADMIN", "TRAINING_ADMIN"] else "Student"

    def get_avatar_color(self, obj: CourseGroupMessage) -> str:
        return get_avatar_color(str(obj.sender_id))

    def get_profile_photo(self, obj: CourseGroupMessage) -> str | None:
        sender = obj.sender
        if sender and sender.profile_photo:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(sender.profile_photo.url)
            return sender.profile_photo.url
        return None

    def get_timestamp(self, obj: CourseGroupMessage) -> str:
        return format_relative_time(obj.created_at)


class CourseGroupListSerializer(serializers.ModelSerializer):
    """Serializer for study groups card list."""

    creator_name = serializers.SerializerMethodField()
    creator_role = serializers.SerializerMethodField()
    creator_id = serializers.UUIDField(source="created_by.id", read_only=True)
    members_count = serializers.SerializerMethodField()
    is_member = serializers.SerializerMethodField()
    can_add_members = serializers.SerializerMethodField()
    can_manage_group = serializers.SerializerMethodField()
    created_at_formatted = serializers.SerializerMethodField()
    last_activity = serializers.SerializerMethodField()
    course_id = serializers.UUIDField(source="course.id", read_only=True)
    course_title = serializers.CharField(source="course.title", read_only=True)

    class Meta:
        model = CourseGroup
        fields = [
            "id",
            "course_id",
            "course_title",
            "name",
            "description",
            "category",
            "creator_id",
            "creator_name",
            "creator_role",
            "allow_students_to_add_members",
            "can_add_members",
            "can_manage_group",
            "members_count",
            "is_member",
            "created_at_formatted",
            "created_at",
            "last_activity",
        ]

    def get_creator_name(self, obj: CourseGroup) -> str:
        creator = obj.created_by
        name = f"{creator.first_name} {creator.last_name}".strip()
        return name if name else (creator.email or "Organizer")

    def get_creator_role(self, obj: CourseGroup) -> str:
        return "Tutor" if obj.created_by.role in ["TUTOR", "SYSTEM_ADMIN", "TRAINING_ADMIN"] else "Student"

    def get_members_count(self, obj: CourseGroup) -> int:
        return obj.members.count()

    def get_is_member(self, obj: CourseGroup) -> bool:
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        return obj.members.filter(id=request.user.id).exists()

    def get_can_add_members(self, obj: CourseGroup) -> bool:
        request = self.context.get("request")
        if not request or not request.user or not request.user.is_authenticated:
            return False
        user = request.user
        # Tutors & Staff/Admins can always add members
        if getattr(user, "role", None) in ["TUTOR", "SYSTEM_ADMIN", "TRAINING_ADMIN", "BRANCH_ADMIN", "STAFF"]:
            return True
        # Group creator can always add members
        if obj.created_by_id == user.id:
            return True

        is_member = obj.members.filter(id=user.id).exists()
        creator = obj.created_by
        creator_is_student = (
            creator
            and getattr(creator, "role", None) not in [
                "TUTOR", "SYSTEM_ADMIN", "TRAINING_ADMIN", "BRANCH_ADMIN", "STAFF"
            ]
        )
        # If group was created by student, any other member can add another member.
        if creator_is_student and is_member:
            return True

        # If tutor created it, tutor can provide that access to others via allow_students_to_add_members
        if obj.allow_students_to_add_members and is_member:
            return True

        return False

    def get_can_manage_group(self, obj: CourseGroup) -> bool:
        request = self.context.get("request")
        if not request or not request.user or not request.user.is_authenticated:
            return False
        user = request.user
        if getattr(user, "role", None) in ["TUTOR", "SYSTEM_ADMIN", "TRAINING_ADMIN", "BRANCH_ADMIN", "STAFF"]:
            return True
        return obj.created_by_id == user.id

    def get_created_at_formatted(self, obj: CourseGroup) -> str:
        return obj.created_at.strftime("%b %d, %Y")

    def get_last_activity(self, obj: CourseGroup) -> str:
        last_msg = obj.messages.filter(is_deleted=False).order_by("-created_at").first()
        dt = last_msg.created_at if last_msg else (obj.updated_at or obj.created_at)
        return format_relative_time(dt)


class CourseGroupDetailSerializer(CourseGroupListSerializer):
    """Detailed group serializer including member roster and chat message history."""

    messages = serializers.SerializerMethodField()
    members = serializers.SerializerMethodField()

    class Meta(CourseGroupListSerializer.Meta):
        fields = CourseGroupListSerializer.Meta.fields + ["messages", "members"]

    def get_messages(self, obj: CourseGroup):
        msgs = obj.messages.filter(is_deleted=False).select_related("sender").order_by("created_at")
        return CourseGroupMessageSerializer(msgs, many=True, context=self.context).data

    def get_members(self, obj: CourseGroup):
        request = self.context.get("request")
        return [
            {
                "id": str(m.id),
                "name": f"{m.first_name} {m.last_name}".strip() or m.email,
                "role": "Instructor" if m.role == "TUTOR" else "Student",
                "student_id": getattr(m, "student_id", None),
                "avatar_color": get_avatar_color(str(m.id)),
                "profile_photo": (
                    request.build_absolute_uri(m.profile_photo.url)
                    if (request and m.profile_photo)
                    else (m.profile_photo.url if m.profile_photo else None)
                ),
                "is_creator": m.id == obj.created_by_id,
            }
            for m in obj.members.all()
        ]


class CourseGroupCreateSerializer(serializers.ModelSerializer):
    """Validation for creating a new group."""

    course_id = serializers.UUIDField(required=False)
    name = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    category = serializers.CharField(max_length=150, required=False, allow_blank=True, default="General")
    allow_students_to_add_members = serializers.BooleanField(required=False, default=False)

    class Meta:
        model = CourseGroup
        fields = ["course_id", "name", "description", "category", "allow_students_to_add_members"]


class CourseGroupUpdateSerializer(serializers.ModelSerializer):
    """Validation for updating group attributes and permissions."""

    name = serializers.CharField(max_length=255, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    category = serializers.CharField(max_length=150, required=False, allow_blank=True)
    allow_students_to_add_members = serializers.BooleanField(required=False)

    class Meta:
        model = CourseGroup
        fields = ["name", "description", "category", "allow_students_to_add_members"]


class CourseGroupMemberAddSerializer(serializers.Serializer):
    """Validation for adding members to a study group."""

    user_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        allow_empty=False,
    )
    user_id = serializers.UUIDField(required=False)

    def validate(self, attrs):
        if not attrs.get("user_ids") and not attrs.get("user_id"):
            raise serializers.ValidationError("Either 'user_id' or 'user_ids' must be provided.")
        return attrs


class CourseGroupMessageCreateSerializer(serializers.Serializer):
    """Validation for posting a message into a group chat."""

    content = serializers.CharField(min_length=1)

