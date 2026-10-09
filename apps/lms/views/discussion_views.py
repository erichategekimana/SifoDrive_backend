"""
apps/lms/views/discussion_views.py
==================================
REST endpoints for course discussion forums, threaded replies, and tutor moderation controls.
"""

from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.mixins import SuccessResponseMixin
from apps.lms.models import Course, DiscussionTopic, DiscussionReply
from apps.lms.serializers.discussion_serializers import (
    DiscussionTopicSerializer,
    DiscussionTopicCreateSerializer,
    DiscussionReplySerializer,
    DiscussionReplyCreateSerializer,
)


def is_user_tutor_or_admin(user) -> bool:
    return (
        getattr(user, "is_tutor", False)
        or getattr(user, "role", "") in ["TUTOR", "SYSTEM_ADMIN", "TRAINING_ADMIN"]
        or user.is_staff
        or user.is_superuser
    )


class CourseDiscussionListCreateView(SuccessResponseMixin, APIView):
    """
    GET  /api/v1/lms/courses/<course_id>/discussions/
         List all active discussion topics for the course.
    POST /api/v1/lms/courses/<course_id>/discussions/
         Create a new discussion topic. Tutors and students can both post!
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, course_id, *args, **kwargs):
        course = get_object_or_404(Course, id=course_id, is_deleted=False)

        is_moderator = is_user_tutor_or_admin(request.user)
        topic_filter = Q(course=course, is_deleted=False)
        if not is_moderator:
            topic_filter &= Q(is_locked=False)

        topics = (
            DiscussionTopic.objects.filter(topic_filter)
            .select_related("author", "course")
            .prefetch_related("liked_by")
            .annotate(
                annotated_replies_count=Count("replies", filter=Q(replies__is_deleted=False))
            )
            .order_by("-is_pinned", "-created_at")
        )

        serializer = DiscussionTopicSerializer(topics, many=True, context={"request": request})
        return self.success_response(data=serializer.data)

    def post(self, request, course_id, *args, **kwargs):
        course = get_object_or_404(Course, id=course_id, is_deleted=False)

        serializer = DiscussionTopicCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return self.validation_error(serializer.errors)

        validated = serializer.validated_data
        topic = DiscussionTopic.objects.create(
            course=course,
            author=request.user,
            title=validated["title"].strip(),
            content=validated["content"].strip(),
            is_pinned=validated.get("is_pinned", False) and is_user_tutor_or_admin(request.user),
        )

        output_serializer = DiscussionTopicSerializer(topic, context={"request": request})
        return self.success_response(
            data=output_serializer.data,
            message="Discussion topic posted successfully.",
            status_code=status.HTTP_201_CREATED,
        )


class DiscussionDetailView(SuccessResponseMixin, APIView):
    """
    GET    /api/v1/lms/discussions/<topic_id>/
           Retrieve discussion topic details along with all threaded replies.
           Constraint: Locked topics are completely invisible to students.
    DELETE /api/v1/lms/discussions/<topic_id>/
           Delete topic. Permitted to tutors, admins, or topic authors.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, topic_id, *args, **kwargs):
        topic = get_object_or_404(
            DiscussionTopic.objects.select_related("author", "course").prefetch_related("liked_by"),
            id=topic_id,
            is_deleted=False,
        )

        is_moderator = is_user_tutor_or_admin(request.user)
        if topic.is_locked and not is_moderator:
            return self.error_response(
                code="NOT_FOUND",
                message="Discussion topic not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        serializer = DiscussionTopicSerializer(
            topic,
            context={"request": request, "include_replies": True},
        )
        return self.success_response(data=serializer.data)

    def delete(self, request, topic_id, *args, **kwargs):
        topic = get_object_or_404(DiscussionTopic, id=topic_id, is_deleted=False)

        is_moderator = is_user_tutor_or_admin(request.user)
        if not is_moderator and topic.author_id != request.user.id:
            return self.error_response(
                code="FORBIDDEN",
                message="You do not have permission to delete this discussion topic.",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        topic.is_deleted = True
        topic.deleted_by = request.user
        topic.save(update_fields=["is_deleted", "deleted_by", "updated_at"])

        return self.success_response(message="Discussion topic deleted successfully.")


class DiscussionLockToggleView(SuccessResponseMixin, APIView):
    """
    POST /api/v1/lms/discussions/<topic_id>/toggle-lock/
         Tutors can lock or unlock discussion topics.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, topic_id, *args, **kwargs):
        topic = get_object_or_404(DiscussionTopic, id=topic_id, is_deleted=False)

        if not is_user_tutor_or_admin(request.user):
            return self.error_response(
                code="FORBIDDEN",
                message="Only tutors and instructors can lock or unlock discussion topics.",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        topic.is_locked = not topic.is_locked
        topic.save(update_fields=["is_locked", "updated_at"])

        status_text = "locked" if topic.is_locked else "unlocked"
        return self.success_response(
            data={"is_locked": topic.is_locked},
            message=f"Discussion has been {status_text}.",
        )


class DiscussionTopicLikeToggleView(SuccessResponseMixin, APIView):
    """
    POST /api/v1/lms/discussions/<topic_id>/toggle-like/
         Like or unlike a discussion topic.
         Constraint: Locked topics are inaccessible to students.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, topic_id, *args, **kwargs):
        topic = get_object_or_404(DiscussionTopic, id=topic_id, is_deleted=False)
        is_moderator = is_user_tutor_or_admin(request.user)
        if topic.is_locked and not is_moderator:
            return self.error_response(
                code="NOT_FOUND",
                message="Discussion topic not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        user = request.user

        if topic.liked_by.filter(id=user.id).exists():
            topic.liked_by.remove(user)
            has_liked = False
        else:
            topic.liked_by.add(user)
            has_liked = True

        return self.success_response(
            data={"has_liked": has_liked, "likes_count": topic.liked_by.count()},
            message="Like status updated.",
        )


class DiscussionReplyCreateView(SuccessResponseMixin, APIView):
    """
    POST /api/v1/lms/discussions/<topic_id>/replies/
         Post a reply to a discussion topic or reply to another reply.
         Constraint: Locked discussions are completely invisible/inaccessible to students.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, topic_id, *args, **kwargs):
        topic = get_object_or_404(DiscussionTopic, id=topic_id, is_deleted=False)

        is_moderator = is_user_tutor_or_admin(request.user)
        if topic.is_locked and not is_moderator:
            return self.error_response(
                code="NOT_FOUND",
                message="Discussion topic not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        serializer = DiscussionReplyCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return self.validation_error(serializer.errors)

        validated = serializer.validated_data
        parent = None
        parent_id = validated.get("parent_id")
        if parent_id:
            parent = get_object_or_404(
                DiscussionReply,
                id=parent_id,
                topic=topic,
                is_deleted=False,
            )

        reply = DiscussionReply.objects.create(
            topic=topic,
            author=request.user,
            parent=parent,
            content=validated["content"].strip(),
        )

        output_serializer = DiscussionReplySerializer(reply, context={"request": request})
        return self.success_response(
            data=output_serializer.data,
            message="Reply submitted successfully.",
            status_code=status.HTTP_201_CREATED,
        )


class DiscussionReplyLikeToggleView(SuccessResponseMixin, APIView):
    """
    POST /api/v1/lms/discussions/<topic_id>/replies/<reply_id>/toggle-like/
         Like or unlike a comment / reply.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, topic_id, reply_id, *args, **kwargs):
        topic = get_object_or_404(DiscussionTopic, id=topic_id, is_deleted=False)
        is_moderator = is_user_tutor_or_admin(request.user)
        if topic.is_locked and not is_moderator:
            return self.error_response(
                code="NOT_FOUND",
                message="Discussion topic not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        reply = get_object_or_404(
            DiscussionReply,
            id=reply_id,
            topic=topic,
            is_deleted=False,
        )
        user = request.user

        if reply.liked_by.filter(id=user.id).exists():
            reply.liked_by.remove(user)
            has_liked = False
        else:
            reply.liked_by.add(user)
            has_liked = True

        return self.success_response(
            data={"has_liked": has_liked, "likes_count": reply.liked_by.count()},
            message="Like status updated.",
        )


class DiscussionReplyDeleteView(SuccessResponseMixin, APIView):
    """
    DELETE /api/v1/lms/discussions/<topic_id>/replies/<reply_id>/
           Delete a reply. Tutors, admins, or reply authors can delete.
    """

    permission_classes = [IsAuthenticated]

    def delete(self, request, topic_id, reply_id, *args, **kwargs):
        reply = get_object_or_404(
            DiscussionReply,
            id=reply_id,
            topic_id=topic_id,
            is_deleted=False,
        )

        is_moderator = is_user_tutor_or_admin(request.user)
        if not is_moderator and reply.author_id != request.user.id:
            return self.error_response(
                code="FORBIDDEN",
                message="You do not have permission to delete this reply.",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        reply.is_deleted = True
        reply.deleted_by = request.user
        reply.save(update_fields=["is_deleted", "deleted_by", "updated_at"])

        return self.success_response(message="Reply deleted successfully.")
