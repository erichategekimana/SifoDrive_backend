from typing import List
from rest_framework.exceptions import ValidationError as ValidationException
from apps.booking.models import CategoryPrice, LicenseCategory


class CategoryPriceService:
    """Service for setting and retrieving booking prices per category."""

    @classmethod
    def get_all_prices(cls) -> List[CategoryPrice]:
        return list(CategoryPrice.objects.all().order_by("category"))

    @classmethod
    def set_price(
        cls,
        category: str,
        price_rwf: int,
        description: str = "",
        is_active: bool = True,
    ) -> CategoryPrice:
        if category not in LicenseCategory.values:
            raise ValidationException(f"Invalid category: {category}")
        if price_rwf < 0:
            raise ValidationException("Price cannot be negative.")

        obj, _ = CategoryPrice.objects.update_or_create(
            category=category,
            defaults={
                "price_rwf": price_rwf,
                "description": description.strip(),
                "is_active": is_active,
            }
        )
        return obj
