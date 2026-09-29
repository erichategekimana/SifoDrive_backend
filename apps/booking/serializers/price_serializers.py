from rest_framework import serializers
from apps.booking.models import CategoryPrice


class CategoryPriceSerializer(serializers.ModelSerializer):
    """Serializer for license category booking pricing."""

    class Meta:
        model = CategoryPrice
        fields = ["id", "category", "price_rwf", "description", "is_active"]
        read_only_fields = ["id"]
