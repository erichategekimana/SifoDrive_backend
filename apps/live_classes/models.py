"""
apps/live_classes/models.py
===========================
Enterprise Live Tutoring, Cohort Management, and Attendance Tracking for Sifo Drive.
Enables administrators to schedule sessions, assign tutors & cohorts,
and track student attendance for driving theory provisional license exam preparation.
NOTE: In accordance with Rwandan provisional driving exam curriculum, content and
students are NOT segmented by license category (universal road safety theory).
"""

from datetime import date, datetime
import logging
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel

logger = logging.getLogger("apps.live_classes.models")


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class LiveClassStatus(models.TextChoices):
    SCHEDULED = "SCHEDULED", _("Scheduled")
    IN_PROGRESS = "IN_PROGRESS", _("In Progress / Live Now")
    COMPLETED = "COMPLETED", _("Completed")
    RESCHEDULED = "RESCHEDULED", _("Rescheduled")
    CANCELLED = "CANCELLED", _("Cancelled")


class AttendanceStatus(models.TextChoices):
    PRESENT = "PRESENT", _("Present")
    LATE = "LATE", _("Late")
    ABSENT = "ABSENT", _("Absent")
    EXCUSED = "EXCUSED", _("Excused")
    WATCHED_RECORDING = "WATCHED_RECORDING", _("Watched Recording")


# ---------------------------------------------------------------------------
# Cohort / Batch Model
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Live Class Session Model
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Attendance Model
# ---------------------------------------------------------------------------

class ClassAttendance(BaseModel):
    """
    Student attendance record for a live class.
    Feeds the 75% live attendance threshold required for provisional mock exam eligibility.
    """

    live_class = models.ForeignKey(
        LiveClass,
        on_delete=models.CASCADE,
        related_name="attendances",
        verbose_name=_("Live Class"),
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="class_attendances",
        verbose_name=_("Student"),
    )
    status = models.CharField(
        _("Attendance Status"),
        max_length=25,
        choices=AttendanceStatus.choices,
        default=AttendanceStatus.PRESENT,
    )
    joined_at = models.DateTimeField(_("Joined At"), null=True, blank=True)
    minutes_attended = models.PositiveIntegerField(
        _("Minutes Attended"),
        default=0,
    )
    marked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="marked_attendances",
        verbose_name=_("Recorded By (Tutor/Admin)"),
    )
    notes = models.CharField(_("Attendance Notes"), max_length=255, blank=True)

    class Meta(BaseModel.Meta):
        verbose_name = _("Class Attendance")
        verbose_name_plural = _("Class Attendances")
        unique_together = [["student", "live_class"]]
        indexes = [
            models.Index(fields=["student", "status"], name="att_student_status_idx"),
            models.Index(fields=["live_class", "status"], name="att_class_status_idx"),
        ]

    def __str__(self):
        return f"{self.student.phone_number} — {self.live_class.title} [{self.status}]"


# ---------------------------------------------------------------------------
# Class Learning Resources Model
# ---------------------------------------------------------------------------

class ClassResource(BaseModel):
    """
    Supplementary learning documents / slides attached to a live class.
    Added by Training Admin or Tutor for students to study before or after session.
    """

    live_class = models.ForeignKey(
        LiveClass,
        on_delete=models.CASCADE,
        related_name="resources",
        verbose_name=_("Live Class"),
    )
    title = models.CharField(_("Resource Title"), max_length=200)
    file = models.FileField(
        _("Attached File"),
        upload_to="live_classes/resources/%Y/%m/",
        null=True,
        blank=True,
        help_text=_("PDF slide deck, worksheet, or summary document"),
    )
    external_link = models.URLField(
        _("External Link"),
        blank=True,
        help_text=_("Google Drive, Figma, or web resource link"),
    )
    description = models.TextField(_("Description"), blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_class_resources",
    )

    class Meta(BaseModel.Meta):
        verbose_name = _("Class Resource")
        verbose_name_plural = _("Class Resources")
        ordering = ["title"]

    def __str__(self):
        return f"{self.title} ({self.live_class.title})"
