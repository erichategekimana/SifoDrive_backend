from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import (
    TrafficLawArticle,
    TrafficLawDefinition,
    TrafficSign,
    RoadMarking,
    PoliceEvaluationQuestion,
    TrafficQuestion,
)


@admin.register(TrafficLawArticle)
class TrafficLawArticleAdmin(admin.ModelAdmin):
    list_display = (
        "article_number",
        "article_label",
        "title",
        "part_roman",
        "part_title",
        "word_count",
        "source_page",
    )
    list_filter = ("part_number", "is_bis")
    search_fields = ("article_label", "title", "content")
    ordering = ("article_number",)
    readonly_fields = ("created_at", "updated_at", "word_count")

    fieldsets = (
        (
            _("Article Identification"),
            {
                "fields": (
                    ("article_number", "article_code", "article_label"),
                    ("part_number", "part_roman", "is_bis"),
                    "part_title",
                )
            },
        ),
        (
            _("Structural Context"),
            {
                "fields": (
                    ("chapter_number", "chapter_title"),
                    ("section_number", "section_title"),
                )
            },
        ),
        (
            _("Content"),
            {
                "fields": (
                    "title",
                    "content",
                    "key_values",
                    ("word_count", "source_page"),
                )
            },
        ),
        (
            _("Audit Timestamps"),
            {
                "classes": ("collapse",),
                "fields": ("created_at", "updated_at"),
            },
        ),
    )


@admin.register(TrafficLawDefinition)
class TrafficLawDefinitionAdmin(admin.ModelAdmin):
    list_display = ("number", "term_rw", "term_fr", "term_en", "article")
    search_fields = ("term_rw", "term_fr", "term_en", "definition_rw")
    ordering = ("number",)
    raw_id_fields = ("article",)


@admin.register(TrafficSign)
class TrafficSignAdmin(admin.ModelAdmin):
    list_display = (
        "thumbnail_preview",
        "code",
        "name_rw",
        "category",
        "source_page",
    )
    list_filter = ("category",)
    search_fields = ("code", "name_rw", "name_fr", "description_rw")
    ordering = ("code",)
    filter_horizontal = ("related_articles",)

    def thumbnail_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="height: 38px; width: auto; object-fit: contain; border-radius: 4px;" />',
                obj.image.url,
            )
        return "-"

    thumbnail_preview.short_description = _("Sign")


@admin.register(RoadMarking)
class RoadMarkingAdmin(admin.ModelAdmin):
    list_display = (
        "thumbnail_preview",
        "marking_code",
        "name_rw",
        "source_page",
    )
    search_fields = ("marking_code", "name_rw", "rule_rw")
    ordering = ("marking_code",)
    filter_horizontal = ("related_articles",)

    def thumbnail_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="height: 38px; width: auto; object-fit: contain; border-radius: 4px;" />',
                obj.image.url,
            )
        return "-"

    thumbnail_preview.short_description = _("Marking")


@admin.register(PoliceEvaluationQuestion)
class PoliceEvaluationQuestionAdmin(admin.ModelAdmin):
    list_display = (
        "question_number",
        "question_snippet",
        "source_page",
    )
    search_fields = ("question_rw", "answer_rw")
    ordering = ("question_number",)
    filter_horizontal = ("related_articles",)

    def question_snippet(self, obj):
        return (obj.question_rw[:90] + "...") if len(obj.question_rw) > 90 else obj.question_rw

    question_snippet.short_description = _("Question")


@admin.register(TrafficQuestion)
class TrafficQuestionAdmin(admin.ModelAdmin):
    list_display = (
        "thumbnail_preview",
        "question_number",
        "question_snippet",
        "correct_choice",
        "source_page",
    )
    list_filter = ("correct_choice",)
    search_fields = ("question_text_rw", "question_text_en", "question_text_fr")
    ordering = ("question_number",)
    filter_horizontal = ("related_articles",)

    def thumbnail_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="height: 38px; width: auto; object-fit: contain; border-radius: 4px;" />',
                obj.image.url,
            )
        return "-"

    thumbnail_preview.short_description = _("Diagram")

    def question_snippet(self, obj):
        text = obj.question_text_rw or obj.question_text_en or obj.question_text_fr
        return (text[:90] + "...") if len(text) > 90 else text

    question_snippet.short_description = _("Question")
