from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class SignCategory(models.TextChoices):
    WARNING = "WARNING", _("Warning / Danger Signs (Ibyapa biburira)")
    PRIORITY = "PRIORITY", _("Priority Signs (Ibyapa by'ubutambike)")
    PROHIBITORY = "PROHIBITORY", _("Prohibitory Signs (Ibyapa bibuza)")
    MANDATORY = "MANDATORY", _("Mandatory Signs (Ibyapa bitegeka)")
    INFORMATORY = "INFORMATORY", _("Informatory Signs (Ibyapa biyobora)")


class TrafficSign(BaseModel):
    """
    Official road traffic signs cataloged from the Official Gazette.
    Contains statutory code, visual crop, multilingual titles, descriptions, and linked articles.
    """

    code = models.CharField(
        _("Sign Code"),
        max_length=30,
        unique=True,
        db_index=True,
        help_text=_("Official statutory sign designation, e.g. 'A.1a', 'B.1', 'C.1a'"),
    )
    category = models.CharField(
        _("Category"),
        max_length=30,
        choices=SignCategory.choices,
        db_index=True,
    )
    name_rw = models.CharField(
        _("Name (Kinyarwanda)"),
        max_length=255,
    )
    name_fr = models.CharField(
        _("Name (French)"),
        max_length=255,
        blank=True,
        default="",
    )
    name_en = models.CharField(
        _("Name (English)"),
        max_length=255,
        blank=True,
        default="",
    )
    description_rw = models.TextField(
        _("Description (Kinyarwanda)"),
        blank=True,
        default="",
    )
    description_fr = models.TextField(
        _("Description (French)"),
        blank=True,
        default="",
    )
    description_en = models.TextField(
        _("Description (English)"),
        blank=True,
        default="",
    )
    image = models.ImageField(
        _("Sign Image"),
        upload_to="traffic_law/signs/",
        null=True,
        blank=True,
    )
    image_path = models.CharField(
        _("Image Relative Path"),
        max_length=255,
        blank=True,
        default="",
        help_text=_("Path relative to media root, e.g. 'traffic_law/signs/sign_A_1a.png'"),
    )
    source_page = models.PositiveSmallIntegerField(
        _("Gazette Source Page"),
        null=True,
        blank=True,
    )
    crop_box = models.JSONField(
        _("Original Crop Box [x, y, w, h]"),
        default=list,
        blank=True,
    )
    related_articles = models.ManyToManyField(
        "TrafficLawArticle",
        related_name="signs",
        blank=True,
        verbose_name=_("Related Articles"),
        help_text=_("Statutory articles governing this sign (Arts 91 to 109)"),
    )

    class Meta(BaseModel.Meta):
        verbose_name = _("Traffic Sign")
        verbose_name_plural = _("Traffic Signs")
        ordering = ["code"]

    def __str__(self) -> str:
        return f"{self.code} - {self.name_rw}"


class RoadMarking(BaseModel):
    """
    Official road surface markings cataloged from Chapter IV of the Official Gazette.
    """

    marking_code = models.CharField(
        _("Marking Code / Reference"),
        max_length=30,
        unique=True,
        db_index=True,
        help_text=_("Statutory marking identifier, e.g. '110.2', '111.1', '114'"),
    )
    name_rw = models.CharField(
        _("Name (Kinyarwanda)"),
        max_length=255,
    )
    name_fr = models.CharField(
        _("Name (French)"),
        max_length=255,
        blank=True,
        default="",
    )
    name_en = models.CharField(
        _("Name (English)"),
        max_length=255,
        blank=True,
        default="",
    )
    rule_rw = models.TextField(
        _("Statutory Rule (Kinyarwanda)"),
        help_text=_("Mandatory driving rule associated with this road marking"),
    )
    rule_fr = models.TextField(
        _("Statutory Rule (French)"),
        blank=True,
        default="",
    )
    rule_en = models.TextField(
        _("Statutory Rule (English)"),
        blank=True,
        default="",
    )
    image = models.ImageField(
        _("Marking Image"),
        upload_to="traffic_law/markings/",
        null=True,
        blank=True,
    )
    image_path = models.CharField(
        _("Image Relative Path"),
        max_length=255,
        blank=True,
        default="",
    )
    source_page = models.PositiveSmallIntegerField(
        _("Gazette Source Page"),
        null=True,
        blank=True,
    )
    related_articles = models.ManyToManyField(
        "TrafficLawArticle",
        related_name="markings",
        blank=True,
        verbose_name=_("Related Articles"),
        help_text=_("Statutory articles governing this marking (Arts 110 to 118)"),
    )

    class Meta(BaseModel.Meta):
        verbose_name = _("Road Marking")
        verbose_name_plural = _("Road Markings")
        ordering = ["marking_code"]

    def __str__(self) -> str:
        return f"{self.marking_code} - {self.name_rw}"
