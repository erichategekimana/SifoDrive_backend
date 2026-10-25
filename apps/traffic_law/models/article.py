from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class TrafficLawArticle(BaseModel):
    """
    Statutory article of the Rwanda Traffic Law
    (Presidential Order No. 85/01 of 02/09/2002 regulating general traffic police and road traffic).
    """

    article_number = models.DecimalField(
        _("Article Number"),
        max_digits=6,
        decimal_places=1,
        unique=True,
        db_index=True,
        help_text=_("Numeric article index. E.g. 1.0, 47.0, 47.1 for 47 bis, 56.1 for 56 bis, 159.0"),
    )
    article_code = models.CharField(
        _("Article Code"),
        max_length=30,
        unique=True,
        db_index=True,
        help_text=_("Unique programmatic identifier, e.g. 'art_1', 'art_47_bis', 'art_159'"),
    )
    article_label = models.CharField(
        _("Article Label"),
        max_length=60,
        help_text=_("Official statutory citation label, e.g. 'Ingingo ya 1', 'Ingingo ya 47 bis'"),
    )
    part_number = models.PositiveSmallIntegerField(
        _("Part Number"),
        db_index=True,
        help_text=_("Statutory Part integer: 1 through 9"),
    )
    part_roman = models.CharField(
        _("Part Roman"),
        max_length=10,
        help_text=_("Roman numeral Part designation: I through IX"),
    )
    part_title = models.CharField(
        _("Part Title"),
        max_length=255,
        help_text=_("Official Part heading"),
    )
    chapter_number = models.CharField(
        _("Chapter Number"),
        max_length=50,
        blank=True,
        default="",
    )
    chapter_title = models.CharField(
        _("Chapter Title"),
        max_length=255,
        blank=True,
        default="",
    )
    section_number = models.CharField(
        _("Section Number"),
        max_length=50,
        blank=True,
        default="",
    )
    section_title = models.CharField(
        _("Section Title"),
        max_length=255,
        blank=True,
        default="",
    )
    title = models.CharField(
        _("Title"),
        max_length=255,
        help_text=_("Descriptive article title in Kinyarwanda/French/English"),
    )
    content = models.TextField(
        _("Verbatim Content"),
        help_text=_("Official verbatim statutory text in Kinyarwanda"),
    )
    word_count = models.PositiveIntegerField(
        _("Word Count"),
        default=0,
    )
    key_values = models.JSONField(
        _("Key Values & Thresholds"),
        default=dict,
        blank=True,
        help_text=_("Structured statutory constants: speed limits, weights, distances, time periods"),
    )
    source_page = models.PositiveSmallIntegerField(
        _("Official Gazette Page"),
        null=True,
        blank=True,
    )
    is_bis = models.BooleanField(
        _("Is Bis Article"),
        default=False,
        help_text=_("True for supplementary articles (e.g. Ingingo ya 47 bis, 56 bis)"),
    )

    class Meta(BaseModel.Meta):
        verbose_name = _("Traffic Law Article")
        verbose_name_plural = _("Traffic Law Articles")
        ordering = ["article_number"]
        indexes = [
            models.Index(fields=["part_number", "article_number"]),
        ]

    def __str__(self) -> str:
        return f"{self.article_label}: {self.title}"

    def save(self, *args, **kwargs) -> None:
        if self.content and not self.word_count:
            self.word_count = len(self.content.split())
        if self.article_number in (47.1, 56.1):
            self.is_bis = True
        super().save(*args, **kwargs)
