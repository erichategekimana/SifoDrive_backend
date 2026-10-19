from rest_framework import serializers

from apps.lms.models import QuizQuestion


class AdminQuizQuestionSerializer(serializers.ModelSerializer):
    """CRUD Serializer for Quiz Questions in LMS / Question Bank Studio with edit audit tracking."""

    last_edited_by_name = serializers.SerializerMethodField()
    last_edited_by_role = serializers.SerializerMethodField()
    last_edited_at = serializers.SerializerMethodField()
    edit_reason = serializers.SerializerMethodField()
    edit_history = serializers.SerializerMethodField()

    _audit_cache = None

    class Meta:
        model = QuizQuestion
        fields = [
            "id",
            "question_number",
            "domain",
            "question_text",
            "question_text_kinyarwanda",
            "question_text_french",
            "option_a",
            "option_b",
            "option_c",
            "option_d",
            "option_a_kinyarwanda",
            "option_b_kinyarwanda",
            "option_c_kinyarwanda",
            "option_d_kinyarwanda",
            "option_a_french",
            "option_b_french",
            "option_c_french",
            "option_d_french",
            "option_a_image",
            "option_b_image",
            "option_c_image",
            "option_d_image",
            "correct_option",
            "explanation",
            "explanation_kinyarwanda",
            "explanation_french",
            "image",
            "is_active",
            "created_at",
            "updated_at",
            "last_edited_by_name",
            "last_edited_by_role",
            "last_edited_at",
            "edit_reason",
            "edit_history",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
            "last_edited_by_name",
            "last_edited_by_role",
            "last_edited_at",
            "edit_reason",
            "edit_history",
        ]

    def _get_audit_entry(self, obj):
        from apps.examinations.services.question_audit_service import load_all_question_edits
        if AdminQuizQuestionSerializer._audit_cache is None:
            AdminQuizQuestionSerializer._audit_cache = load_all_question_edits()
        return AdminQuizQuestionSerializer._audit_cache.get(str(obj.id))

    def get_last_edited_by_name(self, obj):
        info = self._get_audit_entry(obj)
        return info.get("last_edited_by_name") if info else None

    def get_last_edited_by_role(self, obj):
        info = self._get_audit_entry(obj)
        return info.get("last_edited_by_role") if info else None

    def get_last_edited_at(self, obj):
        info = self._get_audit_entry(obj)
        return info.get("last_edited_at") if info else None

    def get_edit_reason(self, obj):
        info = self._get_audit_entry(obj)
        return info.get("edit_reason") if info else None

    def get_edit_history(self, obj):
        info = self._get_audit_entry(obj)
        return info.get("history", []) if info else []

    def validate(self, attrs):
        explanation_rw = attrs.get(
            "explanation_kinyarwanda",
            getattr(self.instance, "explanation_kinyarwanda", None)
        )
        if not explanation_rw or not str(explanation_rw).strip():
            raise serializers.ValidationError(
                {"explanation_kinyarwanda": "Kinyarwanda explanation is required."}
            )

        explanation_en = attrs.get(
            "explanation",
            getattr(self.instance, "explanation", None)
        )
        if not explanation_en or not str(explanation_en).strip():
            raise serializers.ValidationError(
                {"explanation": "English explanation is required."}
            )

        return super().validate(attrs)

    def update(self, instance, validated_data):
        # Question reference number is fixed and cannot be changed
        validated_data.pop("question_number", None)
        return super().update(instance, validated_data)
