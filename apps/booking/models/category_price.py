from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel
from .choices import LicenseCategory


class CategoryPrice(BaseModel):
    """
    Booking fee pricing per license category.
    Managed exclusively by system administrators.
    """

    category = models.CharField(
        _("License Category"),
        max_length=5,
        choices=LicenseCategory.choices,
        unique=True,
        db_index=True,
    )
    price_rwf = models.PositiveIntegerField(
        _("Price (RWF)"),
        help_text=_("Booking service fee in Rwandan Francs (RWF)"),
    )
    description = models.CharField(
        _("Description"),
        max_length=255,
        blank=True,
    )
    is_active = models.BooleanField(
        _("Is Active"),
        default=True,
    )

    class Meta(BaseModel.Meta):
        app_label = "booking"
        verbose_name = _("Category Price")
        verbose_name_plural = _("Category Prices")
        ordering = ["category"]

    def __str__(self):
        return f"Category {self.category}: {self.price_rwf:,} RWF"

    @classmethod
    def get_price_for_category(cls, category: str) -> int:
        """Fetch active price for a category with safe default fallbacks."""
        record = cls.objects.filter(category=category, is_active=True).first()
        if record:
            return record.price_rwf

        # Default standard schedule in RWF if not yet configured by admin
        default_fees = {
            LicenseCategory.A: 5000,
            LicenseCategory.B: 10000,
            LicenseCategory.C: 15000,
            LicenseCategory.D: 15000,
            LicenseCategory.E: 20000,
            LicenseCategory.F: 10000,
        }
        return default_fees.get(category, 10000)
