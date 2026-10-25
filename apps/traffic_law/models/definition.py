from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class TrafficLawDefinition(BaseModel):
    """
    Statutory definition from Article 2 of Presidential Order No. 85/01.
    Maintains official terms in Kinyarwanda and French, with full definition text.
    """

    number = models.PositiveSmallIntegerField(
        _("Definition Index"),
        unique=True,
        db_index=True,
        help_text=_("Sequential index 1 through 43"),
    )
    term_rw = models.CharField(
        _("Term (Kinyarwanda)"),
        max_length=150,
        db_index=True,
        help_text=_("Official term in Kinyarwanda, e.g. 'Inzira Nyabagendwa'"),
    )
    term_fr = models.CharField(
        _("Term (French)"),
        max_length=150,
        db_index=True,
        help_text=_("Official legal French equivalent, e.g. 'Voie publique'"),
    )
    term_en = models.CharField(
        _("Term (English)"),
        max_length=150,
        blank=True,
        default="",
        help_text=_("English translation, e.g. 'Public road'"),
    )
    definition_rw = models.TextField(
        _("Definition (Kinyarwanda)"),
        help_text=_("Verbatim statutory definition in Kinyarwanda"),
    )
    definition_fr = models.TextField(
        _("Definition (French)"),
        blank=True,
        default="",
    )
    definition_en = models.TextField(
        _("Definition (English)"),
        blank=True,
        default="",
    )
    article = models.ForeignKey(
        "TrafficLawArticle",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="definitions",
        verbose_name=_("Source Article"),
        help_text=_("Linked statutory article (Article 2)"),
    )

    class Meta(BaseModel.Meta):
        verbose_name = _("Traffic Law Definition")
        verbose_name_plural = _("Traffic Law Definitions")
        ordering = ["number"]

    def __str__(self) -> str:
        return f"{self.number}. {self.term_rw} ({self.term_fr})"
