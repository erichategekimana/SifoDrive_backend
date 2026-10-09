"""
apps/lms/models/discussion.py
=============================
Course discussion forums and threaded conversations for students and tutors.
"""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class DiscussionTopic(BaseModel):
    """
    A discussion forum topic/thread within a course.
    Both tutors and students can create topics.
    Tutors have moderation privileges: lock, unlock, pin, delete.
    """

    course = models.ForeignKey(
        "lms.Course",
        on_delete=models.CASCADE,
        related_name="discussion_topics",
        verbose_name=_("Course"),
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="authored_discussions",
        verbose_name=_("Author"),
    )
    title = models.CharField(_("Title"), max_length=255)
    content = models.TextField(_("Content"))
    is_locked = models.BooleanField(
        _("Is Locked"),
        default=False,
        db_index=True,
        help_text=_("When locked, students cannot add replies. Tutors can lock/unlock."),
    )
    is_pinned = models.BooleanField(_("Is Pinned"), default=False, db_index=True)
    liked_by = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="liked_discussion_topics",
        blank=True,
        verbose_name=_("Liked By"),
    )

    class Meta:
        verbose_name = _("Discussion Topic")
        verbose_name_plural = _("Discussion Topics")
        ordering = ["-is_pinned", "-created_at"]

    def __str__(self) -> str:
        return f"{self.title} ({self.course.title})"


class DiscussionReply(BaseModel):
    """
    A threaded reply to a discussion topic or another reply.
    """

    topic = models.ForeignKey(
        DiscussionTopic,
        on_delete=models.CASCADE,
        related_name="replies",
        verbose_name=_("Discussion Topic"),
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="authored_discussion_replies",
        verbose_name=_("Author"),
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
        verbose_name=_("Parent Reply"),
        help_text=_("Optional parent reply for nested replies."),
    )
    content = models.TextField(_("Content"))
    liked_by = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="liked_discussion_replies",
        blank=True,
        verbose_name=_("Liked By"),
    )

    class Meta:
        verbose_name = _("Discussion Reply")
        verbose_name_plural = _("Discussion Replies")
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"Reply by {self.author} on {self.topic.title}"
