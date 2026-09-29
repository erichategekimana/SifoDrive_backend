"""
apps/lms/serializers/road_sign_serializers.py
==============================================
Serializers for Rwandan Road Signs.
"""

from rest_framework import serializers
from apps.lms.models.content import RoadSign


class RoadSignSerializer(serializers.ModelSerializer):
    class Meta:
        model = RoadSign
        fields = [
            "id", "name", "sign_code", "category",
            "image", "description", "description_kinyarwanda",
            "is_active",
        ]
        read_only_fields = ["id"]
