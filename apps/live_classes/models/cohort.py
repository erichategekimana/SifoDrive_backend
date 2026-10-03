from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class CohortStatus(models.TextChoices):
    QUEUE = "queue", _("Queue")
    OPEN = "open", _("Open")
    CLOSED = "closed", _("Closed")
    ENDED = "ended", _("Ended")


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
    max_capacity = models.PositiveIntegerField(_("Max Capacity"), default=60)
    sequence_number = models.PositiveIntegerField(
        _("Sequence Number"),
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        help_text=_("Auto-incrementing integer sequence starting from 1"),
    )
    identifier = models.CharField(
        _("3-digit Identifier"),
        max_length=10,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        help_text=_("3-digit auto-generated identifier, e.g. 001, 002"),
    )
    status = models.CharField(
        _("Cohort Status"),
        max_length=20,
        choices=CohortStatus.choices,
        default=CohortStatus.QUEUE,
        db_index=True,
        help_text=_(
            "queue: waiting in queue, open: default cohort for new registered students, "
            "closed: capacity reached or closed by admin, ended: scheduled time reached"
        ),
    )
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
        return f"{self.name} [{self.identifier or '---'}] ({self.code})"

    def save(self, *args, **kwargs):
        if not self.sequence_number:
            max_seq = Cohort.objects.aggregate(models.Max("sequence_number"))["sequence_number__max"] or 0
            self.sequence_number = max_seq + 1
        if not self.identifier:
            self.identifier = f"{self.sequence_number:03d}"
        super().save(*args, **kwargs)

    @property
    def student_count(self) -> int:
        return self.students.count()

    @property
    def tutor_count(self) -> int:
        return self.assigned_tutors.count()

    def evaluate_status(self, save: bool = True) -> str:
        """
        Evaluate and auto-transition cohort status based on:
        1. End date passed -> 'ended'
        2. Capacity reached when 'open' -> 'closed'
        """
        from django.utils import timezone
        today = timezone.now().date()
        changed = False

        if self.end_date and self.end_date < today:
            if self.status != CohortStatus.ENDED:
                self.status = CohortStatus.ENDED
                changed = True
        elif self.status == CohortStatus.OPEN and self.students.count() >= self.max_capacity:
            self.status = CohortStatus.CLOSED
            changed = True

        if changed and save:
            self.save(update_fields=["status", "updated_at"])

        return self.status
