from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel
from apps.live_classes.models.choices import AttendanceStatus
from apps.live_classes.models.live_class import LiveClass


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
        app_label = 'live_classes'
        verbose_name = _("Class Attendance")
        verbose_name_plural = _("Class Attendances")
        unique_together = [["student", "live_class"]]
        indexes = [
            models.Index(fields=["student", "status"], name="att_student_status_idx"),
            models.Index(fields=["live_class", "status"], name="att_class_status_idx"),
        ]

    def __str__(self):
        return f"{self.student.phone_number} — {self.live_class.title} [{self.status}]"
