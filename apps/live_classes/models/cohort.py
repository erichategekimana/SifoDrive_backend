from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class Cohort(BaseModel):
    """
    Learning group / batch of students assigned to specific tutors and timetables.
    Managed by System Admin and Training Admin.
    """

    name = models.CharField(_("Cohort Name"), max_length=150)
    code = models.CharField(
        _("Cohort Code"),
        max_length=50,
        unique=True,
        db_index=True,
        help_text=_("Unique identifier, e.g. COHORT-2026-SEP-AM"),
    )
    description = models.CharField(
        _("Description"),
        max_length=165,
        blank=True,
        help_text=_("Cohort summary (max 165 characters)"),
    )
    assigned_tutors = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="assigned_cohorts",
        blank=True,
        verbose_name=_("Assigned Tutors / Teachers"),
    )
    students = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="enrolled_cohorts",
        blank=True,
        verbose_name=_("Enrolled Students"),
    )
    start_date = models.DateField(_("Start Date"))
    end_date = models.DateField(_("End Date"), null=True, blank=True)
    max_capacity = models.PositiveIntegerField(_("Max Capacity"), default=50)
    is_active = models.BooleanField(_("Is Active"), default=True, db_index=True)
    schedule_description = models.CharField(
        _("Schedule Description"),
        max_length=255,
        blank=True,
        help_text=_("e.g. Mon, Wed, Fri 09:00 - 11:00 CAT"),
    )

    class Meta(BaseModel.Meta):
        app_label = 'live_classes'
        verbose_name = _("Cohort")
        verbose_name_plural = _("Cohorts")
        ordering = ["-start_date", "name"]

    def __str__(self):
        return f"{self.name} ({self.code})"

    @property
    def student_count(self) -> int:
        return self.students.count()

    @property
    def tutor_count(self) -> int:
        return self.assigned_tutors.count()
