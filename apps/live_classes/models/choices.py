from django.db import models
from django.utils.translation import gettext_lazy as _


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
