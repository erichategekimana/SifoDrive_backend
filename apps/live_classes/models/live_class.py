from datetime import date, datetime
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel
from apps.live_classes.models.choices import LiveClassStatus
from apps.live_classes.models.cohort import Cohort


class LiveClass(BaseModel):
    """
    A live Google Meet tutoring session.
    Scheduled and managed by Admin; delivered and moderated by Tutors.
    """

    title = models.CharField(_("Title"), max_length=200)
    topic = models.CharField(_("Topic"), max_length=300, blank=True)
    cohort = models.ForeignKey(
        Cohort,
        on_delete=models.CASCADE,
        related_name="live_classes",
        null=True,
        blank=True,
        verbose_name=_("Assigned Cohort"),
        help_text=_("Specific student cohort, or blank for platform-wide open class"),
    )
    tutor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="tutored_classes",
        verbose_name=_("Tutor / Teacher"),
    )
    module = models.ForeignKey(
        "lms.Module",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="live_classes",
        verbose_name=_("Related Curriculum Module"),
    )
    lesson = models.ForeignKey(
        "lms.Lesson",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="live_classes",
        verbose_name=_("Related Lesson"),
    )
    scheduled_date = models.DateField(_("Scheduled Date"), db_index=True)
    start_time = models.TimeField(_("Start Time"))
    end_time = models.TimeField(_("End Time"))
    google_meet_url = models.URLField(
        _("Google Meet URL"),
        help_text=_("Google Meet conference link for this session"),
    )
    status = models.CharField(
        _("Status"),
        max_length=25,
        choices=LiveClassStatus.choices,
        default=LiveClassStatus.SCHEDULED,
        db_index=True,
    )
    is_published = models.BooleanField(
        _("Is Published"),
        default=False,
        db_index=True,
        help_text=_("Whether the class is visible on student timetables"),
    )
    notes = models.TextField(
        _("Session Notes / Syllabus Instructions"),
        blank=True,
    )
    recording_url = models.URLField(
        _("Recording URL"),
        blank=True,
        help_text=_("Link to cloud recording (Drive / YouTube Unlisted / CDN)"),
    )
    actual_started_at = models.DateTimeField(_("Actual Started At"), null=True, blank=True)
    actual_ended_at = models.DateTimeField(_("Actual Ended At"), null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_live_classes",
    )

    class Meta(BaseModel.Meta):
        app_label = 'live_classes'
        verbose_name = _("Live Class")
        verbose_name_plural = _("Live Classes")
        ordering = ["scheduled_date", "start_time"]
        indexes = [
            models.Index(fields=["scheduled_date", "status"], name="lc_date_status_idx"),
            models.Index(fields=["cohort", "scheduled_date"], name="lc_cohort_date_idx"),
        ]

    def __str__(self):
        tutor_str = f" — {self.tutor.get_full_name() or self.tutor.phone_number}" if self.tutor else ""
        return f"{self.title} ({self.scheduled_date} {self.start_time.strftime('%H:%M')}){tutor_str}"

    @property
    def is_past(self) -> bool:
        today = date.today()
        return self.scheduled_date < today or (
            self.scheduled_date == today and self.end_time < datetime.now().time()
        )

    def start_session(self) -> None:
        self.status = LiveClassStatus.IN_PROGRESS
        self.actual_started_at = timezone.now()
        self.save(update_fields=["status", "actual_started_at", "updated_at"])

    def end_session(self, recording_url: str = "") -> None:
        self.status = LiveClassStatus.COMPLETED
        self.actual_ended_at = timezone.now()
        if recording_url:
            self.recording_url = recording_url.strip()
        self.save(update_fields=["status", "actual_ended_at", "recording_url", "updated_at"])
