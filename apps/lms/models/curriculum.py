"""
apps/lms/models/curriculum.py
==============================
Curriculum and Course domain models.

Architecture:
  Curriculum ──< Course ──< Module ──< Lesson

Publish lifecycle:
  Curriculum → has is_published / publish() / unpublish()
  Course     → has is_published / publish() / unpublish()

Only SYSTEM_ADMIN can create and manage Curricula.
"""

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel, OrderedModel  # noqa: F401 (re-exported via __init__)


class Curriculum(OrderedModel):
    """
    Overarching educational framework (e.g. 'Universal Rwanda Driving Theory').
    A Curriculum contains multiple Courses.
    Only SYSTEM_ADMIN can create and manage Curricula.
    """

    title = models.CharField(_("Title"), max_length=200)
    title_kinyarwanda = models.CharField(
        _("Title (Kinyarwanda)"), max_length=200, blank=True, default=""
    )
    code = models.CharField(
        _("Code"),
        max_length=50,
        unique=True,
        blank=True,
        null=True,
        help_text=_("Curriculum identifier, e.g. RW-CURR-UNIVERSAL"),
    )
    description = models.TextField(_("Description"), blank=True, default="")
    description_kinyarwanda = models.TextField(
        _("Description (Kinyarwanda)"), blank=True, default=""
    )
    thumbnail = models.ImageField(
        _("Thumbnail"),
        upload_to="lms/curricula/thumbnails/",
        null=True,
        blank=True,
        help_text=_("Curriculum cover image."),
    )

    # ── Authorship ──────────────────────────────────────────────────────────
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_curricula",
        verbose_name=_("Created By"),
    )
    updated_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_curricula",
        verbose_name=_("Last Updated By"),
    )

    # ── Publish lifecycle ────────────────────────────────────────────────────
    is_published = models.BooleanField(_("Published"), default=False, db_index=True)
    published_at = models.DateTimeField(_("Published At"), null=True, blank=True)
    published_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="published_curricula",
        verbose_name=_("Published By"),
    )

    class Meta(OrderedModel.Meta):
        verbose_name = _("Curriculum")
        verbose_name_plural = _("Curricula")

    def __str__(self) -> str:
        status = "✓" if self.is_published else "draft"
        return f"[{status}] {self.title}"

    @property
    def course_count(self) -> int:
        return self.courses.filter(is_deleted=False).count()

    @property
    def published_course_count(self) -> int:
        return self.courses.filter(is_published=True, is_deleted=False).count()

    def publish(self, published_by=None) -> None:
        """Make this curriculum live. Idempotent."""
        if self.is_published:
            return
        self.is_published = True
        self.published_at = timezone.now()
        if published_by:
            self.published_by = published_by
        self.save(update_fields=["is_published", "published_at", "published_by", "updated_at"])

    def unpublish(self) -> None:
        """Pull curriculum back to draft state. Cascades unpublish to child courses."""
        if not self.is_published:
            return
        self.is_published = False
        self.save(update_fields=["is_published", "updated_at"])
        # Child courses cannot remain published under an unpublished curriculum
        for course in self.courses.filter(is_published=True):
            course.unpublish()


class Course(OrderedModel):
    """
    Learning container within a Curriculum (e.g. 'Road Regulations & Traffic Signs').
    A Curriculum contains multiple Courses, each Course contains multiple Modules.
    """

    curriculum = models.ForeignKey(
        Curriculum,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="courses",
        verbose_name=_("Curriculum"),
        help_text=_("Parent curriculum containing this course."),
    )
    code = models.CharField(
        _("Code"),
        max_length=50,
        blank=True,
        default="",
        help_text=_("Course code identifier, e.g. RWT-01."),
    )
    title = models.CharField(_("Title"), max_length=200)
    title_kinyarwanda = models.CharField(
        _("Title (Kinyarwanda)"), max_length=200, blank=True, default=""
    )
    description = models.TextField(_("Description"), blank=True)
    description_kinyarwanda = models.TextField(
        _("Description (Kinyarwanda)"), blank=True, default=""
    )
    thumbnail = models.ImageField(
        _("Thumbnail"),
        upload_to="lms/courses/thumbnails/",
        null=True,
        blank=True,
        help_text=_("Course card image shown in the course catalogue."),
    )
    estimated_hours = models.PositiveSmallIntegerField(
        _("Estimated Hours"),
        default=0,
        help_text=_("Approximate time to complete this course in hours."),
    )

    # ── Authorship ──────────────────────────────────────────────────────────
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_courses",
        verbose_name=_("Created By"),
    )
    updated_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_courses",
        verbose_name=_("Last Updated By"),
    )

    # ── Publish lifecycle ────────────────────────────────────────────────────
    is_published = models.BooleanField(_("Published"), default=False, db_index=True)
    published_at = models.DateTimeField(_("Published At"), null=True, blank=True)
    published_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="published_courses",
        verbose_name=_("Published By"),
    )

    class Meta(OrderedModel.Meta):
        verbose_name = _("Course")
        verbose_name_plural = _("Courses")

    def __str__(self) -> str:
        status = "✓" if self.is_published else "draft"
        return f"[{status}] {self.title}"

    # ── Computed properties ──────────────────────────────────────────────────

    @property
    def module_count(self) -> int:
        return self.modules.filter(is_deleted=False).count()

    @property
    def lesson_count(self) -> int:
        from apps.lms.models.content import Lesson
        return Lesson.objects.filter(
            module__course=self,
            module__is_deleted=False,
            is_deleted=False,
        ).count()

    @property
    def published_module_count(self) -> int:
        return self.modules.filter(is_published=True, is_deleted=False).count()

    # ── Lifecycle methods ────────────────────────────────────────────────────

    def publish(self, published_by=None) -> None:
        """Make this course live. Requires parent curriculum to be published."""
        if self.curriculum and not self.curriculum.is_published:
            from django.core.exceptions import ValidationError
            raise ValidationError(
                f"Cannot publish course '{self.title}' because parent curriculum '{self.curriculum.title}' is not published."
            )
        if self.is_published:
            return
        self.is_published = True
        self.published_at = timezone.now()
        if published_by:
            self.published_by = published_by
        self.save(update_fields=["is_published", "published_at", "published_by", "updated_at"])

    def unpublish(self) -> None:
        """Pull course back to draft state. Idempotent."""
        if not self.is_published:
            return
        self.is_published = False
        self.save(update_fields=["is_published", "updated_at"])

