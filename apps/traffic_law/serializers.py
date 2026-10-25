from rest_framework import serializers

from .models import (
    TrafficLawArticle,
    TrafficLawDefinition,
    TrafficSign,
    RoadMarking,
    PoliceEvaluationQuestion,
    TrafficQuestion,
)


class TrafficLawArticleListSerializer(serializers.ModelSerializer):
    class Meta:
        model = TrafficLawArticle
        fields = [
            "id",
            "article_number",
            "article_code",
            "article_label",
            "part_number",
            "part_roman",
            "part_title",
            "chapter_number",
            "chapter_title",
            "title",
            "word_count",
            "source_page",
            "is_bis",
        ]


class TrafficLawArticleDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = TrafficLawArticle
        fields = [
            "id",
            "article_number",
            "article_code",
            "article_label",
            "part_number",
            "part_roman",
            "part_title",
            "chapter_number",
            "chapter_title",
            "section_number",
            "section_title",
            "title",
            "content",
            "word_count",
            "key_values",
            "source_page",
            "is_bis",
        ]


class TrafficLawDefinitionSerializer(serializers.ModelSerializer):
    source_article_code = serializers.CharField(source="article.article_code", read_only=True)

    class Meta:
        model = TrafficLawDefinition
        fields = [
            "id",
            "number",
            "term_rw",
            "term_fr",
            "term_en",
            "definition_rw",
            "definition_fr",
            "definition_en",
            "source_article_code",
        ]


class TrafficSignSerializer(serializers.ModelSerializer):
    related_article_codes = serializers.SerializerMethodField()

    class Meta:
        model = TrafficSign
        fields = [
            "id",
            "code",
            "category",
            "name_rw",
            "name_fr",
            "name_en",
            "description_rw",
            "description_fr",
            "description_en",
            "image",
            "image_path",
            "source_page",
            "crop_box",
            "related_article_codes",
        ]

    def get_related_article_codes(self, obj):
        return [a.article_code for a in obj.related_articles.all()]


class RoadMarkingSerializer(serializers.ModelSerializer):
    related_article_codes = serializers.SerializerMethodField()

    class Meta:
        model = RoadMarking
        fields = [
            "id",
            "marking_code",
            "name_rw",
            "name_fr",
            "name_en",
            "rule_rw",
            "rule_fr",
            "rule_en",
            "image",
            "image_path",
            "source_page",
            "related_article_codes",
        ]

    def get_related_article_codes(self, obj):
        return [a.article_code for a in obj.related_articles.all()]


class PoliceEvaluationQuestionSerializer(serializers.ModelSerializer):
    related_article_codes = serializers.SerializerMethodField()

    class Meta:
        model = PoliceEvaluationQuestion
        fields = [
            "id",
            "question_number",
            "question_rw",
            "answer_rw",
            "source_page",
            "related_article_codes",
        ]

    def get_related_article_codes(self, obj):
        return [a.article_code for a in obj.related_articles.all()]


class TrafficQuestionSerializer(serializers.ModelSerializer):
    related_article_codes = serializers.SerializerMethodField()

    class Meta:
        model = TrafficQuestion
        fields = [
            "id",
            "question_number",
            "question_text_rw",
            "question_text_en",
            "question_text_fr",
            "options",
            "correct_choice",
            "explanation_rw",
            "explanation_en",
            "explanation_fr",
            "image",
            "image_path",
            "domain_tags",
            "source_page",
            "related_article_codes",
        ]

    def get_related_article_codes(self, obj):
        return [a.article_code for a in obj.related_articles.all()]
