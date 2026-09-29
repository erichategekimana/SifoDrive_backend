from rest_framework import serializers

from apps.examinations.models import (
    Certificate,
    CertificateTemplate,
)


class CertificateTemplateSerializer(serializers.ModelSerializer):
    """Administrative serializer for customizing certificate templates."""

    class Meta:
        model = CertificateTemplate
        fields = [
            "id",
            "template_type",
            "header_subtitle",
            "title",
            "conferral_text",
            "course_name",
            "declaration_text",
            "confirmation_notes",
            "logo_url",
            "training_admin_name",
            "training_admin_title",
            "training_admin_signature",
            "director_name",
            "director_title",
            "director_signature",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class CertificateSerializer(serializers.ModelSerializer):
    """Serializer for issued official certificates."""

    class Meta:
        model = Certificate
        fields = [
            "id",
            "certificate_number",
            "student_name",
            "student_code",
            "track_type",
            "enterprise_name",
            "started_at",
            "completed_at",
            "score",
            "total_questions",
            "passing_score",
            "passed",
            "issue_date",
            "verification_hash",
            "verification_url",
            "template_snapshot",
            "is_valid",
            "created_at",
        ]
        read_only_fields = fields
