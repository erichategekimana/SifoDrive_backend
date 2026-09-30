from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel, UUIDModel
from apps.accounts.constants import UserRole
from apps.accounts.models.user import User


class TutorProfile(UUIDModel, TimeStampedModel):
    """
    Profile data for Theory & Practical driving instructors/facilitators.
    Maintains instructor accreditation, Google Meet classroom credentials,
    and assigned learner cohort capacity.
    """

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="tutor_profile",
        limit_choices_to={"role": UserRole.TUTOR},
    )
    tutor_code = models.CharField(
        _("Tutor Code"),
        max_length=30,
        unique=True,
        db_index=True,
        help_text=_("Unique identifier (e.g. SIFO-TUT-001)."),
    )
    title = models.CharField(
        _("Professional Title"),
        max_length=120,
        default="Theory & Practical Driving Instructor",
        help_text=_("e.g. Senior Traffic Law Instructor, Category B Specialist"),
    )
    bio = models.TextField(
        _("Instructor Biography"),
        blank=True,
        default="",
    )
    specialization_categories = models.JSONField(
        _("Specialization License Categories"),
        default=list,
        blank=True,
        help_text=_("List of license categories taught, e.g. ['A', 'B', 'C']."),
    )
    default_meeting_url = models.URLField(
        _("Default Google Meet URL"),
        max_length=500,
        blank=True,
        default="",
        help_text=_("Permanent Google Meet link used for recurring live sessions."),
    )
    is_available_for_tutoring = models.BooleanField(
        _("Available for Tutoring"),
        default=True,
    )
    max_student_capacity = models.PositiveIntegerField(
        _("Maximum Student Capacity"),
        default=50,
        help_text=_("Maximum concurrent learners assigned to this instructor."),
    )
    total_teaching_hours = models.PositiveIntegerField(
        _("Total Teaching Hours"),
        default=0,
    )
    rating = models.DecimalField(
        _("Instructor Rating"),
        max_digits=3,
        decimal_places=2,
        default=5.00,
    )

    class Meta:
        app_label = "accounts"
        verbose_name = _("Tutor Profile")
        verbose_name_plural = _("Tutor Profiles")
        ordering = ["tutor_code"]

    def __str__(self) -> str:
        return f"Tutor {self.tutor_code} — {self.user.full_name or self.user.phone_number}"

    @property
    def active_students_count(self) -> int:
        """Count of students currently assigned to this tutor."""
        return self.user.tutoring_students.filter(is_active=True).count()
