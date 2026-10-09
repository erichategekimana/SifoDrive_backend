"""
apps/lms/models/group.py
========================
Course study groups and collaborative group chat for students and tutors.
"""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class CourseGroup(BaseModel):
    """
    A student or tutor created study group within a course.
    Members can join and participate in real-time group chat.
    """

    course = models.ForeignKey(
        "lms.Course",
        on_delete=models.CASCADE,
        related_name="groups",
        verbose_name=_("Course"),
    )
    name = models.CharField(_("Group Name"), max_length=255)
    description = models.TextField(_("Description"), blank=True, default="")
    category = models.CharField(_("Topic Category"), max_length=150, default="General")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_course_groups",
        verbose_name=_("Created By"),
    )
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="joined_course_groups",
        blank=True,
        verbose_name=_("Members"),
    )

    class Meta:
        verbose_name = _("Course Group")
        verbose_name_plural = _("Course Groups")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name} ({self.course.title})"


class CourseGroupMessage(BaseModel):
    """
    A chat message sent within a CourseGroup.
    """

    group = models.ForeignKey(
        CourseGroup,
        on_delete=models.CASCADE,
        related_name="messages",
        verbose_name=_("Group"),
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="course_group_messages",
        verbose_name=_("Sender"),
    )
    content = models.TextField(_("Message Content"))

    class Meta:
        verbose_name = _("Course Group Message")
        verbose_name_plural = _("Course Group Messages")
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"Message by {self.sender} in {self.group.name}"
