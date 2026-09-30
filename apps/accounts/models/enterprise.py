from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel, UUIDModel
from apps.accounts.constants import UserRole
from apps.accounts.models.user import User


class EnterpriseProfile(UUIDModel, TimeStampedModel):
    """
    Profile data for Driving Schools (B2B Enterprise accounts).
    Tracks institutional accreditation, computer lab hardware station quotas,
    and batch student test seat allowances.
    """

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="enterprise_profile",
        limit_choices_to={"role": UserRole.ENTERPRISE_ADMIN},
    )
    school_name = models.CharField(
        _("Driving School Name"),
        max_length=200,
        help_text=_("Official registered driving school name."),
    )
    registration_number = models.CharField(
        _("RDB / MININFRA Registration Number"),
        max_length=50,
        unique=True,
        db_index=True,
        help_text=_("Official business and accreditation license number."),
    )
    district = models.CharField(
        _("District"),
        max_length=50,
        default="Kigali",
        help_text=_("District where driving school campus is located."),
    )
    sector = models.CharField(
        _("Sector"),
        max_length=50,
        blank=True,
        default="",
    )
    address_line = models.CharField(
        _("Campus Address"),
        max_length=255,
        blank=True,
        default="",
    )
    contact_email = models.EmailField(
        _("Official Contact Email"),
        blank=True,
        default="",
    )
    contact_phone = models.CharField(
        _("Contact Phone Number"),
        max_length=20,
        blank=True,
        default="",
    )
    concurrent_station_quota = models.PositiveSmallIntegerField(
        _("Licensed Concurrent Lab Stations"),
        default=20,
        help_text=_("Maximum concurrent hardware exam workstations allowed for this school."),
    )
    is_verified_school = models.BooleanField(
        _("Verified Driving School"),
        default=True,
    )

    class Meta:
        app_label = "accounts"
        verbose_name = _("Enterprise Profile")
        verbose_name_plural = _("Enterprise Profiles")
        ordering = ["school_name"]

    def __str__(self) -> str:
        return f"{self.school_name} (Quota: {self.concurrent_station_quota})"
