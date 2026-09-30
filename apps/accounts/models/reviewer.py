from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel, UUIDModel
from apps.accounts.constants import UserRole
from apps.accounts.models.user import User


class ReviewerProfile(UUIDModel, TimeStampedModel):
    """
    Profile data for Board Reviewers / Internal Integrity Examiners.
    Tracks reviewer accreditation credentials, flagged exam audit history,
    and proctoring violation adjudication records.
    """

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="reviewer_profile",
        limit_choices_to={"role": UserRole.BOARD_REVIEWER},
    )
    reviewer_code = models.CharField(
        _("Reviewer Code"),
        max_length=30,
        unique=True,
        db_index=True,
        help_text=_("Unique identifier (e.g. SIFO-REV-001)."),
    )
    inspector_badge_number = models.CharField(
        _("Inspector Badge / License Number"),
        max_length=50,
        blank=True,
        default="",
        help_text=_("Official inspection or regulatory authority badge number."),
    )
    accreditation_authority = models.CharField(
        _("Accreditation Authority"),
        max_length=150,
        default="Rwanda National Police / Sifo Board of Examiners",
    )
    total_reviews_completed = models.PositiveIntegerField(
        _("Total Reviews Completed"),
        default=0,
    )
    total_certifications_approved = models.PositiveIntegerField(
        _("Total Certifications Approved"),
        default=0,
    )
    total_violations_confirmed = models.PositiveIntegerField(
        _("Total Violations Confirmed"),
        default=0,
    )
    is_active_reviewer = models.BooleanField(
        _("Is Active Reviewer"),
        default=True,
    )

    class Meta:
        app_label = "accounts"
        verbose_name = _("Reviewer Profile")
        verbose_name_plural = _("Reviewer Profiles")
        ordering = ["reviewer_code"]

    def __str__(self) -> str:
        return f"Reviewer {self.reviewer_code} — {self.user.full_name or self.user.phone_number}"
