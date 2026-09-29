from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel, UUIDModel
from apps.accounts.constants import LicenseCategory, UserRole
from apps.accounts.models.user import User


class StudentProfile(UUIDModel, TimeStampedModel):
    """
    Extended profile data for enrolled students.
    Separate from User to keep the core User model lean.
    """

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="student_profile",
        limit_choices_to={"role": UserRole.STUDENT},
    )
    preferred_language = models.CharField(
        _("Preferred Language"),
        max_length=10,
        choices=[("en", "English"), ("rw", "Kinyarwanda")],
        default="en",
    )
    license_category = models.CharField(
        _("License Category"),
        max_length=5,
        choices=LicenseCategory.choices,
        default=LicenseCategory.B,
    )
    enrollment_date = models.DateField(
        _("Enrollment Date"),
        null=True,
        blank=True,
    )

    # --- Gamification ---
    current_streak_days = models.PositiveIntegerField(
        _("Current Streak (Days)"),
        default=0,
    )
    longest_streak_days = models.PositiveIntegerField(
        _("Longest Streak (Days)"),
        default=0,
    )
    last_activity_date = models.DateField(
        _("Last Activity Date"),
        null=True,
        blank=True,
    )

    class Meta:
        app_label = 'accounts'
        verbose_name = _("Student Profile")
        verbose_name_plural = _("Student Profiles")

    def __str__(self) -> str:
        return f"Profile — {self.user.student_id or self.user.phone_number}"
