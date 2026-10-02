"""
apps/lms/models/cohort_content.py
=================================
Cohort-specific module releases and quiz schedules managed by tutors.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class CohortModuleRelease(BaseModel):
    """
    Cohort-specific release and lock configuration for a module.
    Allows tutors to release or lock learning modules independently per cohort.
    """

    cohort = models.ForeignKey(
        "live_classes.Cohort",
        on_delete=models.CASCADE,
        related_name="module_releases",
        verbose_name=_("Cohort"),
    )
    module = models.ForeignKey(
        "lms.Module",
        on_delete=models.CASCADE,
        related_name="cohort_releases",
        verbose_name=_("Module"),
    )
    is_published = models.BooleanField(
        _("Published to Cohort"),
        default=True,
        db_index=True,
        help_text=_("Whether students in this cohort can access this module."),
    )
    is_locked = models.BooleanField(
        _("Locked for Cohort"),
        default=False,
        db_index=True,
        help_text=_("Whether this module is locked for students in this cohort."),
    )
    unlock_date = models.DateTimeField(
        _("Scheduled Unlock Date"),
        null=True,
        blank=True,
        help_text=_("Automatic unlock time for students in this cohort."),
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_module_releases",
        verbose_name=_("Updated By"),
    )

    class Meta(BaseModel.Meta):
        unique_together = ("cohort", "module")
        verbose_name = _("Cohort Module Release")
        verbose_name_plural = _("Cohort Module Releases")

    def __str__(self) -> str:
        state = "Unlocked" if not self.is_locked else "Locked"
        pub = "Published" if self.is_published else "Draft"
        return f"{self.cohort.name} → {self.module.title} [{pub}, {state}]"

    @property
    def is_currently_unlocked(self) -> bool:
        if not self.is_published:
            return False
        if not self.is_locked:
            return True
        if self.unlock_date and self.unlock_date <= timezone.now():
            return True
        return False


class CohortQuizSchedule(BaseModel):
    """
    Cohort-specific schedule, release state, and deadline for a quiz.
    Managed by the tutor instructing this cohort.
    """

    cohort = models.ForeignKey(
        "live_classes.Cohort",
        on_delete=models.CASCADE,
        related_name="quiz_schedules",
        verbose_name=_("Cohort"),
    )
    quiz = models.ForeignKey(
        "lms.Quiz",
        on_delete=models.CASCADE,
        related_name="cohort_schedules",
        verbose_name=_("Quiz"),
    )
    is_published = models.BooleanField(
        _("Published to Cohort"),
        default=False,
        db_index=True,
        help_text=_("Controls whether students in this cohort can view/attempt this quiz."),
    )
    is_locked = models.BooleanField(
        _("Locked for Cohort"),
        default=False,
        db_index=True,
        help_text=_("Locks the quiz temporarily for this cohort."),
    )
    open_date = models.DateTimeField(
        _("Open Date"),
        null=True,
        blank=True,
        help_text=_("Date and time when the quiz becomes available to this cohort."),
    )
    deadline = models.DateTimeField(
        _("Deadline / Due Date"),
        null=True,
        blank=True,
        help_text=_("Standard due date for this cohort."),
    )
    extended_deadline = models.DateTimeField(
        _("Extended Deadline"),
        null=True,
        blank=True,
        help_text=_("Tutor-granted extended deadline for this cohort."),
    )
    extension_reason = models.TextField(
        _("Extension Reason"),
        blank=True,
        default="",
        help_text=_("Tutor explanation for deadline extension."),
    )
    scheduled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scheduled_cohort_quizzes",
        verbose_name=_("Scheduled By"),
    )

    class Meta(BaseModel.Meta):
        unique_together = ("cohort", "quiz")
        verbose_name = _("Cohort Quiz Schedule")
        verbose_name_plural = _("Cohort Quiz Schedules")

    def __str__(self) -> str:
        return f"{self.cohort.name} → {self.quiz.title}"

    @property
    def effective_deadline(self):
        return self.extended_deadline or self.deadline

    @property
    def status_for_cohort(self) -> str:
        """
        Status evaluation for this cohort:
        - 'DRAFT': not published
        - 'LOCKED': published but locked
        - 'SCHEDULED': open date is in the future
        - 'CLOSED': effective deadline has passed
        - 'OPEN': currently accessible
        """
        if not self.is_published:
            return "DRAFT"
        if self.is_locked:
            return "LOCKED"
        now = timezone.now()
        if self.open_date and self.open_date > now:
            return "SCHEDULED"
        if self.effective_deadline and self.effective_deadline < now:
            return "CLOSED"
        return "OPEN"
