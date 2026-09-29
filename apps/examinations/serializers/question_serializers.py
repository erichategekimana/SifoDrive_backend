from rest_framework import serializers

from apps.lms.models import QuizQuestion


class AdminQuizQuestionSerializer(serializers.ModelSerializer):
    """CRUD Serializer for Quiz Questions in LMS / Question Bank Studio."""

    class Meta:
        model = QuizQuestion
        fields = [
            "id",
            "question_number",
            "domain",
            "difficulty",
            "question_text",
            "question_text_kinyarwanda",
            "option_a",
            "option_b",
            "option_c",
            "option_d",
            "option_a_kinyarwanda",
            "option_b_kinyarwanda",
            "option_c_kinyarwanda",
            "option_d_kinyarwanda",
            "option_a_image",
            "option_b_image",
            "option_c_image",
            "option_d_image",
            "correct_option",
            "explanation",
            "explanation_kinyarwanda",
            "image",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
