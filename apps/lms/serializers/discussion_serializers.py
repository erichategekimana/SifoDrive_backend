"""
apps/lms/serializers/discussion_serializers.py
==============================================
Serializers for course discussion topics and threaded replies.
"""

from rest_framework import serializers

from apps.lms.models import DiscussionTopic, DiscussionReply


class DiscussionReplySerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()
    author_role = serializers.CharField(source="author.role", read_only=True)
    author_photo = serializers.SerializerMethodField()
    is_author_tutor = serializers.SerializerMethodField()
    parent_id = serializers.UUIDField(source="parent.id", read_only=True, allow_null=True)
    date = serializers.SerializerMethodField()
    likes_count = serializers.SerializerMethodField()
    has_liked = serializers.SerializerMethodField()

    class Meta:
        model = DiscussionReply
        fields = [
            "id",
            "topic_id",
            "author_id",
            "author_name",
            "author_role",
            "author_photo",
            "is_author_tutor",
            "parent_id",
            "content",
            "likes_count",
            "has_liked",
            "date",
            "created_at",
            "updated_at",
        ]

    def get_author_name(self, obj) -> str:
        if not obj.author:
            return "Participant"
        full = f"{obj.author.first_name} {obj.author.last_name}".strip()
        return full or obj.author.phone_number or "Participant"

    def get_author_photo(self, obj) -> str | None:
        if obj.author and obj.author.profile_photo:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.author.profile_photo.url)
            return obj.author.profile_photo.url
        return None

    def get_is_author_tutor(self, obj) -> bool:
        if not obj.author:
            return False
        return (
            getattr(obj.author, "is_tutor", False)
            or getattr(obj.author, "role", "") == "TUTOR"
            or obj.author.is_staff
        )

    def get_date(self, obj) -> str:
        return obj.created_at.strftime("%b %d, %Y at %H:%M") if obj.created_at else ""

    def get_likes_count(self, obj) -> int:
        return obj.liked_by.count()

    def get_has_liked(self, obj) -> bool:
        request = self.context.get("request")
        if not request or not request.user or not request.user.is_authenticated:
            return False
        return obj.liked_by.filter(id=request.user.id).exists()


class DiscussionTopicSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()
    author_role = serializers.CharField(source="author.role", read_only=True)
    author_photo = serializers.SerializerMethodField()
    is_author_tutor = serializers.SerializerMethodField()
    replies_count = serializers.SerializerMethodField()
    likes_count = serializers.SerializerMethodField()
    has_liked = serializers.SerializerMethodField()
    date = serializers.SerializerMethodField()
    replies = serializers.SerializerMethodField()

    class Meta:
        model = DiscussionTopic
        fields = [
            "id",
            "course_id",
            "author_id",
            "author_name",
            "author_role",
            "author_photo",
            "is_author_tutor",
            "title",
            "content",
            "is_locked",
            "is_pinned",
            "replies_count",
            "likes_count",
            "has_liked",
            "date",
            "created_at",
            "updated_at",
            "replies",
        ]

    def get_author_name(self, obj) -> str:
        if not obj.author:
            return "Participant"
        full = f"{obj.author.first_name} {obj.author.last_name}".strip()
        return full or obj.author.phone_number or "Participant"

    def get_author_photo(self, obj) -> str | None:
        if obj.author and obj.author.profile_photo:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.author.profile_photo.url)
            return obj.author.profile_photo.url
        return None

    def get_is_author_tutor(self, obj) -> bool:
        if not obj.author:
            return False
        return (
            getattr(obj.author, "is_tutor", False)
            or getattr(obj.author, "role", "") == "TUTOR"
            or obj.author.is_staff
        )

    def get_replies_count(self, obj) -> int:
        if hasattr(obj, "annotated_replies_count"):
            return obj.annotated_replies_count
        return obj.replies.filter(is_deleted=False).count()

    def get_likes_count(self, obj) -> int:
        return obj.liked_by.count()

    def get_has_liked(self, obj) -> bool:
        request = self.context.get("request")
        if not request or not request.user or not request.user.is_authenticated:
            return False
        return obj.liked_by.filter(id=request.user.id).exists()

    def get_date(self, obj) -> str:
        return obj.created_at.strftime("%b %d, %Y at %H:%M") if obj.created_at else ""

    def get_replies(self, obj):
        # Only return replies if requested or on detail view
        if self.context.get("include_replies", False):
            active_replies = (
                obj.replies.filter(is_deleted=False)
                .select_related("author", "parent")
                .prefetch_related("liked_by")
                .order_by("created_at")
            )
            return DiscussionReplySerializer(active_replies, many=True, context=self.context).data
        return []


class DiscussionTopicCreateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255)
    content = serializers.CharField()
    is_pinned = serializers.BooleanField(default=False, required=False)


class DiscussionReplyCreateSerializer(serializers.Serializer):
    content = serializers.CharField()
    parent_id = serializers.UUIDField(required=False, allow_null=True)
