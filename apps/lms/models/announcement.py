"""
apps/lms/models/announcement.py
================================
Course and cohort-level announcement bulletins authored by tutors and administrators.
"""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class AnnouncementTargetType(models.TextChoices):
    SINGLE_COHORT = "SINGLE_COHORT", _("Single Cohort")
    ALL_ASSIGNED_COHORTS = "ALL_ASSIGNED_COHORTS", _("All Assigned Cohorts")
    COURSE_WIDE = "COURSE_WIDE", _("Course-wide (All Students)")


class Announcement(BaseModel):
    """
    Official notices, schedule updates, and exam briefings authored by tutors & administrators.
    Can be targeted to a single cohort or broadcast across all cohorts assigned to the tutor.
    """

    course = models.ForeignKey(
        "lms.Course",
        on_delete=models.CASCADE,
        related_name="announcements",
        verbose_name=_("Course"),
        null=True,
        blank=True,
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="authored_announcements",
        verbose_name=_("Author"),
    )
    title = models.CharField(_("Title"), max_length=255)
    content = models.TextField(_("Content"))
    category = models.CharField(
        _("Category"),
        max_length=50,
        default="COURSE",
        help_text=_("e.g. COURSE, TRAINING, SYSTEM, TECH"),
    )
    is_pinned = models.BooleanField(_("Is Pinned"), default=False)

    target_type = models.CharField(
        _("Target Audience"),
        max_length=30,
        choices=AnnouncementTargetType.choices,
        default=AnnouncementTargetType.ALL_ASSIGNED_COHORTS,
        db_index=True,
    )
    cohort = models.ForeignKey(
        "live_classes.Cohort",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="single_cohort_announcements",
        verbose_name=_("Specific Target Cohort"),
    )
    cohorts = models.ManyToManyField(
        "live_classes.Cohort",
        blank=True,
        related_name="cohort_announcements",
        verbose_name=_("Target Cohorts"),
    )

    class Meta:
        verbose_name = _("Announcement")
        verbose_name_plural = _("Announcements")
        ordering = ["-is_pinned", "-created_at"]

    def __str__(self) -> str:
        return f"{self.title} ({self.get_target_type_display()})"
