from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class PoliceEvaluationQuestion(BaseModel):
    """
    Official Police self-evaluation questions and answers published in the Official Gazette (pages 89 to 105).
    Covers Q1 through Q224 with exact verified answers and cross-references to statutory articles.
    """

    question_number = models.PositiveIntegerField(
        _("Question Number"),
        unique=True,
        db_index=True,
        help_text=_("Official magazine question number (1 through 224)"),
    )
    question_rw = models.TextField(
        _("Question (Kinyarwanda)"),
    )
    answer_rw = models.TextField(
        _("Answer (Kinyarwanda)"),
    )
    source_page = models.PositiveSmallIntegerField(
        _("Gazette Source Page"),
        help_text=_("Page number in Official Gazette (pages 89 to 105)"),
    )
    related_articles = models.ManyToManyField(
        "TrafficLawArticle",
        related_name="police_evaluations",
        blank=True,
        verbose_name=_("Related Articles"),
        help_text=_("Statutory articles referenced by or explaining this question"),
    )

    class Meta(BaseModel.Meta):
        verbose_name = _("Police Evaluation Question")
        verbose_name_plural = _("Police Evaluation Questions")
        ordering = ["question_number"]

    def __str__(self) -> str:
        snippet = (self.question_rw[:75] + "...") if len(self.question_rw) > 75 else self.question_rw
        return f"Q{self.question_number}: {snippet}"


class TrafficQuestion(BaseModel):
    """
    Companion driving school theory test questions (401 items) in three languages (RW, EN, FR)
    with multi-choice options, answer keys, visual scenario diagrams, and domain tags.
    """

    question_number = models.PositiveIntegerField(
        _("Question Number"),
        unique=True,
        db_index=True,
    )
    question_text_rw = models.TextField(
        _("Question Text (Kinyarwanda)"),
        blank=True,
        default="",
    )
    question_text_en = models.TextField(
        _("Question Text (English)"),
        blank=True,
        default="",
    )
    question_text_fr = models.TextField(
        _("Question Text (French)"),
        blank=True,
        default="",
    )
    options = models.JSONField(
        _("Options"),
        default=dict,
        help_text=_("Structured choices: {'a': {'kinyarwanda': '...', 'english': '...', 'french': '...'}, ...}"),
    )
    correct_choice = models.CharField(
        _("Correct Choice"),
        max_length=5,
        blank=True,
        default="",
        help_text=_("Correct option letter: 'a', 'b', 'c', or 'd'"),
    )
    explanation_rw = models.TextField(
        _("Explanation (Kinyarwanda)"),
        blank=True,
        default="",
    )
    explanation_en = models.TextField(
        _("Explanation (English)"),
        blank=True,
        default="",
    )
    explanation_fr = models.TextField(
        _("Explanation (French)"),
        blank=True,
        default="",
    )
    image = models.ImageField(
        _("Diagram Image"),
        upload_to="traffic_law/questions/",
        null=True,
        blank=True,
    )
    image_path = models.CharField(
        _("Image Relative Path"),
        max_length=255,
        blank=True,
        default="",
    )
    domain_tags = models.JSONField(
        _("Domain Tags"),
        default=list,
        blank=True,
        help_text=_("Subject tags: ['signs', 'priority', 'rules_of_the_road', 'speed_limits', 'parking']"),
    )
    source_page = models.PositiveSmallIntegerField(
        _("Companion PDF Source Page"),
        null=True,
        blank=True,
    )
    related_articles = models.ManyToManyField(
        "TrafficLawArticle",
        related_name="practice_questions",
        blank=True,
        verbose_name=_("Related Articles"),
    )

    class Meta(BaseModel.Meta):
        verbose_name = _("Traffic Question")
        verbose_name_plural = _("Traffic Questions")
        ordering = ["question_number"]

    def __str__(self) -> str:
        text = self.question_text_rw or self.question_text_en or self.question_text_fr
        snippet = (text[:75] + "...") if len(text) > 75 else text
        return f"Q{self.question_number}: {snippet}"
