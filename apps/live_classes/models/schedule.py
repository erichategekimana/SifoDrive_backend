from datetime import date
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel
from apps.live_classes.models.cohort import Cohort


class LiveClassSchedule(BaseModel):
    """
    A master schedule representing a recurring or single live class course offering.
    Managed by Admins; individual LiveClass session occurrences are linked to this schedule.
    """

    title = models.CharField(_("Title"), max_length=200)
    topic = models.CharField(_("Topic"), max_length=300, blank=True)
    cohort = models.ForeignKey(
        Cohort,
        on_delete=models.CASCADE,
        related_name="class_schedules",
        null=True,
        blank=True,
        verbose_name=_("Assigned Cohort"),
    )
    tutor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tutored_schedules",
        verbose_name=_("Assigned Tutor"),
    )
    schedule_mode = models.CharField(
        _("Schedule Mode"),
        max_length=20,
        choices=[("RECURRING", "Recurring Series"), ("SINGLE", "Single Session")],
        default="RECURRING",
    )
    days_of_week = models.JSONField(
        _("Days of Week"),
        default=list,
        help_text=_("List of integer weekdays (0=Mon, 1=Tue, ..., 6=Sun)"),
    )
    start_time = models.TimeField(_("Start Time"))
    end_time = models.TimeField(_("End Time"))
    start_date = models.DateField(_("Start Date"))
    end_date = models.DateField(_("End Date"), null=True, blank=True)
    period_months = models.PositiveIntegerField(_("Period Value"), default=3)
    period_unit = models.CharField(_("Period Unit"), max_length=10, default="months")
    google_meet_url = models.URLField(
        _("Google Meet URL"),
        blank=True,
        help_text=_("Google Meet conference link for this schedule"),
    )
    is_published = models.BooleanField(_("Is Published"), default=True)
    notes = models.TextField(_("Notes"), blank=True)
    is_active = models.BooleanField(_("Is Active"), default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_schedules",
    )

    class Meta(BaseModel.Meta):
        app_label = "live_classes"
        verbose_name = _("Live Class Schedule")
        verbose_name_plural = _("Live Class Schedules")
        ordering = ["-created_at"]

    def __str__(self):
        cohort_str = f" [{self.cohort.name}]" if self.cohort else ""
        return f"{self.title}{cohort_str} ({self.start_date} to {self.end_date or 'single'})"

    @property
    def next_upcoming_session(self):
        return self.sessions.filter(
            scheduled_date__gte=date.today(),
            status__in=["SCHEDULED", "IN_PROGRESS"],
        ).order_by("scheduled_date", "start_time").first()

    @property
    def total_sessions_count(self) -> int:
        return self.sessions.count()
