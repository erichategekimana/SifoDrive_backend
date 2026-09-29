from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel
from apps.live_classes.models.live_class import LiveClass


class ClassResource(BaseModel):
    """
    Supplementary learning documents / slides attached to a live class.
    Added by Training Admin or Tutor for students to study before or after session.
    """

    live_class = models.ForeignKey(
        LiveClass,
        on_delete=models.CASCADE,
        related_name="resources",
        verbose_name=_("Live Class"),
    )
    title = models.CharField(_("Resource Title"), max_length=200)
    file = models.FileField(
        _("Attached File"),
        upload_to="live_classes/resources/%Y/%m/",
        null=True,
        blank=True,
        help_text=_("PDF slide deck, worksheet, or summary document"),
    )
    external_link = models.URLField(
        _("External Link"),
        blank=True,
        help_text=_("Google Drive, Figma, or web resource link"),
    )
    description = models.TextField(_("Description"), blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_class_resources",
    )

    class Meta(BaseModel.Meta):
        app_label = 'live_classes'
        verbose_name = _("Class Resource")
        verbose_name_plural = _("Class Resources")
        ordering = ["title"]

    def __str__(self):
        return f"{self.title} ({self.live_class.title})"
