"""
apps/lms/serializers/quiz_serializers.py
=========================================
Serializers for quiz questions, quiz question items, and quizzes.
"""

from django.db import models, transaction
from rest_framework import serializers

from apps.accounts.constants import UserRole
from apps.lms.models.quiz import Quiz, QuizQuestion, QuizQuestionItem
from .road_sign_serializers import RoadSignSerializer


# ===========================================================================
# Quiz Question
# ===========================================================================

class QuizQuestionListSerializer(serializers.ModelSerializer):
    """Question bank list serializer with localized aliases and staff-aware answer exposure."""

    question_text_rw = serializers.CharField(source="question_text_kinyarwanda", read_only=True)
    option_a_rw = serializers.CharField(source="option_a_kinyarwanda", read_only=True)
    option_b_rw = serializers.CharField(source="option_b_kinyarwanda", read_only=True)
    option_c_rw = serializers.CharField(source="option_c_kinyarwanda", read_only=True)
    option_d_rw = serializers.CharField(source="option_d_kinyarwanda", read_only=True)
    explanation_rw = serializers.CharField(source="explanation_kinyarwanda", read_only=True)

    class Meta:
        model = QuizQuestion
        fields = [
            "id", "question_number", "domain", "difficulty",
            "question_text", "question_text_kinyarwanda", "question_text_rw",
            "option_a", "option_b", "option_c", "option_d",
            "option_a_kinyarwanda", "option_b_kinyarwanda", "option_c_kinyarwanda", "option_d_kinyarwanda",
            "option_a_rw", "option_b_rw", "option_c_rw", "option_d_rw",
            "correct_option", "explanation", "explanation_kinyarwanda", "explanation_rw",
            "image",
            "option_a_image", "option_b_image", "option_c_image", "option_d_image",
            "road_sign",
        ]
        read_only_fields = ["id"]

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        request = self.context.get("request")
        user = getattr(request, "user", None)
        # Protect answer keys if accessed by regular students
        if user and getattr(user, "role", None) == UserRole.STUDENT:
            ret.pop("correct_option", None)
            ret.pop("explanation", None)
            ret.pop("explanation_kinyarwanda", None)
            ret.pop("explanation_rw", None)
        return ret


class QuizQuestionDetailSerializer(serializers.ModelSerializer):
    """Full serializer including correct answer — for tutors, admins, and post-quiz reveal."""

    correct_text = serializers.CharField(read_only=True)
    road_sign_detail = RoadSignSerializer(source="road_sign", read_only=True)

    class Meta:
        model = QuizQuestion
        fields = [
            "id", "question_number", "domain", "difficulty",
            "question_text", "question_text_kinyarwanda",
            "option_a", "option_b", "option_c", "option_d",
            "option_a_kinyarwanda", "option_b_kinyarwanda", "option_c_kinyarwanda", "option_d_kinyarwanda",
            "correct_option", "correct_text",
            "explanation", "explanation_kinyarwanda",
            "image",
            "option_a_image", "option_b_image", "option_c_image", "option_d_image",
            "road_sign", "road_sign_detail",
            "is_active", "created_by",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "correct_text"]


class QuizQuestionWriteSerializer(serializers.ModelSerializer):
    """Write serializer — used by tutors and admins to create/update questions."""

    class Meta:
        model = QuizQuestion
        fields = [
            "question_number", "domain", "difficulty",
            "question_text", "question_text_kinyarwanda",
            "option_a", "option_b", "option_c", "option_d",
            "option_a_kinyarwanda", "option_b_kinyarwanda", "option_c_kinyarwanda", "option_d_kinyarwanda",
            "correct_option", "explanation", "explanation_kinyarwanda",
            "image",
            "option_a_image", "option_b_image", "option_c_image", "option_d_image",
            "road_sign", "is_active",
        ]

    def validate_correct_option(self, value):
        if value.upper() not in ("A", "B", "C", "D"):
            raise serializers.ValidationError("Correct option must be A, B, C, or D.")
        return value.upper()


# ===========================================================================
# Quiz & QuizQuestionItem (Quiz Bank / Course Assessment Engine)
# ===========================================================================

class QuizQuestionItemSerializer(serializers.ModelSerializer):
    original_question = serializers.PrimaryKeyRelatedField(
        queryset=QuizQuestion.objects.all(),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = QuizQuestionItem
        fields = [
            "id", "sort_order", "original_question",
            "points", "question_text", "question_text_kinyarwanda",
            "option_a", "option_b", "option_c", "option_d",
            "option_a_kinyarwanda", "option_b_kinyarwanda", "option_c_kinyarwanda", "option_d_kinyarwanda",
            "correct_option", "explanation", "explanation_kinyarwanda",
            "domain", "difficulty",
        ]
        read_only_fields = ["id"]


class QuizCreatorSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    phone_number = serializers.CharField(read_only=True)
    first_name = serializers.CharField(read_only=True)
    last_name = serializers.CharField(read_only=True)
    full_name = serializers.SerializerMethodField()
    role = serializers.CharField(read_only=True)

    def get_full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}".strip() or obj.phone_number


class QuizListSerializer(serializers.ModelSerializer):
    course_title = serializers.CharField(source="course.title", read_only=True)
    module_title = serializers.CharField(source="module.title", read_only=True, default=None)
    created_by_detail = QuizCreatorSerializer(source="created_by", read_only=True)
    question_count = serializers.IntegerField(read_only=True)
    status = serializers.CharField(read_only=True)
    calculated_total_points = serializers.IntegerField(read_only=True)

    class Meta:
        model = Quiz
        fields = [
            "id", "course", "course_title", "module", "module_title",
            "title", "title_kinyarwanda", "description", "description_kinyarwanda",
            "open_date", "deadline", "time_limit_minutes", "total_score",
            "calculated_total_points", "passing_score", "max_attempts",
            "shuffle_questions", "is_published", "status", "question_count",
            "created_by", "created_by_detail", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "status", "question_count", "calculated_total_points", "created_at", "updated_at"]


class QuizDetailSerializer(QuizListSerializer):
    items = QuizQuestionItemSerializer(many=True, read_only=True)

    class Meta(QuizListSerializer.Meta):
        fields = QuizListSerializer.Meta.fields + [
            "rubric", "rubric_kinyarwanda", "items",
        ]


class QuizWriteSerializer(serializers.ModelSerializer):
    items = QuizQuestionItemSerializer(many=True, required=False)

    class Meta:
        model = Quiz
        fields = [
            "id", "course", "module", "title", "title_kinyarwanda",
            "description", "description_kinyarwanda",
            "open_date", "deadline", "time_limit_minutes",
            "total_score", "passing_score", "rubric", "rubric_kinyarwanda",
            "max_attempts", "shuffle_questions", "is_published", "items",
        ]
        read_only_fields = ["id"]

    def validate(self, attrs):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        items = attrs.get("items", [])

        # System Admin restriction: cannot author from scratch
        if user and getattr(user, "role", None) == UserRole.SYSTEM_ADMIN:
            for idx, item in enumerate(items):
                if not item.get("original_question"):
                    raise serializers.ValidationError({
                        "items": (
                            f"System Admin may only build quizzes using items pulled from the Question Bank. "
                            f"Question #{idx + 1} ('{item.get('question_text', '')[:30]}...') is authored from scratch. "
                            f"Scratch authoring is reserved for Training Admin."
                        )
                    })

        # Calculate total_score from sum of question item points
        if items:
            attrs["total_score"] = sum(max(1, int(item.get("points", 1))) for item in items)
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        items_data = validated_data.pop("items", [])
        if items_data:
            validated_data["total_score"] = sum(max(1, int(item.get("points", 1))) for item in items_data)
        request = self.context.get("request")
        if request and request.user and request.user.is_authenticated:
            validated_data["created_by"] = request.user
        quiz = Quiz.objects.create(**validated_data)
        for idx, item_data in enumerate(items_data):
            sort_order = item_data.pop("sort_order", idx + 1)
            QuizQuestionItem.objects.create(quiz=quiz, sort_order=sort_order, **item_data)
        if items_data:
            total = quiz.items.aggregate(total=models.Sum("points"))["total"]
            if total is not None and total > 0:
                quiz.total_score = total
                quiz.save(update_fields=["total_score"])
        return quiz

    @transaction.atomic
    def update(self, instance, validated_data):
        items_data = validated_data.pop("items", None)
        if items_data is not None and len(items_data) > 0:
            validated_data["total_score"] = sum(max(1, int(item.get("points", 1))) for item in items_data)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if items_data is not None:
            instance.items.all().delete()
            for idx, item_data in enumerate(items_data):
                sort_order = item_data.pop("sort_order", idx + 1)
                QuizQuestionItem.objects.create(quiz=instance, sort_order=sort_order, **item_data)
            total = instance.items.aggregate(total=models.Sum("points"))["total"]
            if total is not None and total > 0:
                instance.total_score = total
                instance.save(update_fields=["total_score"])
        return instance
