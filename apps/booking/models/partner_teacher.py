from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class PartnerTeacher(BaseModel):
    """
    Private driving instructors partnered with Sifo Drive.
    Managed by administrators; selectable by students during booking.
    """

    first_name = models.CharField(_("First Name"), max_length=100)
    last_name = models.CharField(_("Last Name"), max_length=100)
    phone_number = models.CharField(_("Phone Number"), max_length=25, db_index=True)
    driving_school_affiliation = models.CharField(
        _("Affiliated Driving School"),
        max_length=150,
        blank=True,
        help_text=_("e.g. Inyange Driving School or Independent Instructor"),
    )
    is_active = models.BooleanField(_("Is Active"), default=True)
    notes = models.TextField(_("Internal Notes"), blank=True)

    class Meta(BaseModel.Meta):
        app_label = "booking"
        verbose_name = _("Partner Driving Teacher")
        verbose_name_plural = _("Partner Driving Teachers")
        ordering = ["first_name", "last_name"]

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    def __str__(self):
        school = f" - {self.driving_school_affiliation}" if self.driving_school_affiliation else ""
        return f"{self.full_name} ({self.phone_number}){school}"
