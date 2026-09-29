from rest_framework import serializers

from apps.live_classes.models import ClassResource


class ClassResourceSerializer(serializers.ModelSerializer):
    """Serializer for supplementary study materials attached to a class."""
    uploaded_by_name = serializers.CharField(source="uploaded_by.get_full_name", read_only=True)

    class Meta:
        model = ClassResource
        fields = [
            "id",
            "live_class",
            "title",
            "file",
            "external_link",
            "description",
            "uploaded_by",
            "uploaded_by_name",
            "created_at",
        ]
        read_only_fields = ["id", "uploaded_by", "uploaded_by_name", "created_at"]


class ClassResourceCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClassResource
        fields = [
            "title",
            "file",
            "external_link",
            "description",
        ]

    def validate(self, attrs):
        if not attrs.get("file") and not attrs.get("external_link"):
            raise serializers.ValidationError("Either an uploaded file or an external link must be provided.")
        return attrs
