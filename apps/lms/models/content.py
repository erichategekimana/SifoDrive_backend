"""
apps/lms/models/content.py
===========================
Module, Lesson, RoadSign, and LessonQuestion models.

These form the content layer of the LMS:
  Course ──< Module ──< Lesson
  Lesson (ROAD_SIGN type) ──> RoadSign
  Lesson (QUIZ type) ──< LessonQuestion ──> QuizQuestion
"""

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel, OrderedModel
from apps.lms.models.choices import LessonType, RoadSignCategory
from apps.lms.models.curriculum import Course


# ===========================================================================
# Road Sign Reference Bank
# ===========================================================================

class RoadSign(BaseModel):
    """
    Master reference for all Rwanda road signs and road markings.

    Signs are used in:
      - ROAD_SIGN type Lessons (direct FK on Lesson.road_sign)
      - QuizQuestion (FK on QuizQuestion.road_sign)

    Accessible to all authenticated users (guests and students alike).
    """

    name = models.CharField(_("Sign Name"), max_length=200)
    sign_code = models.CharField(
        _("Official Sign Code"),
        max_length=20,
        blank=True,
        help_text=_("Official Rwanda RTDA sign code, e.g. W1, P2, M3."),
    )
    category = models.CharField(
        _("Category"),
        max_length=20,
        choices=RoadSignCategory.choices,
        db_index=True,
    )
    image = models.ImageField(_("Sign Image"), upload_to="lms/road_signs/")
    description = models.TextField(_("Description (English)"))
    description_kinyarwanda = models.TextField(_("Description (Kinyarwanda)"), blank=True)
    is_active = models.BooleanField(_("Active"), default=True, db_index=True)

    class Meta(BaseModel.Meta):
        verbose_name = _("Road Sign")
        verbose_name_plural = _("Road Signs")
        ordering = ["category", "name"]

    def __str__(self) -> str:
        code = f" ({self.sign_code})" if self.sign_code else ""
        return f"{self.name}{code} — {self.get_category_display()}"


# ===========================================================================
# Module
# ===========================================================================

class Module(OrderedModel):
    """
    A thematic section within a Course (e.g., 'Priority Rules at Intersections').

    is_foundational → must be 100% complete for exam eligibility.
    is_published    → controls learner visibility (inherits from course publish state).
    """

    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="modules",
        verbose_name=_("Course"),
    )
    title = models.CharField(_("Title"), max_length=200)
    description = models.TextField(_("Description"), blank=True)
    is_foundational = models.BooleanField(
        _("Foundational"),
        default=False,
        db_index=True,
        help_text=_(
            "Foundational modules must be 100% complete before a student "
            "is eligible to sit the driving theory exam."
        ),
    )

    # ── Access control flags ─────────────────────────────────────────────────
    is_student_only = models.BooleanField(
        _("Student Only"),
        default=False,
        db_index=True,
        help_text=_(
            "If True, this module is only available to registered students and staff. "
            "Guests cannot view this module."
        ),
    )

    # ── Publish lifecycle ────────────────────────────────────────────────────
    is_published = models.BooleanField(_("Published"), default=False, db_index=True)
    published_at = models.DateTimeField(_("Published At"), null=True, blank=True)
    published_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="published_modules",
        verbose_name=_("Published By"),
    )

    class Meta(OrderedModel.Meta):
        verbose_name = _("Module")
        verbose_name_plural = _("Modules")

    def __str__(self) -> str:
        flag = "★" if self.is_foundational else " "
        return f"[{flag}] {self.course.title} › {self.title}"

    @property
    def lesson_count(self) -> int:
        return self.lessons.filter(is_deleted=False).count()

    def publish(self, published_by=None) -> None:
        if self.is_published:
            return
        self.is_published = True
        self.published_at = timezone.now()
        if published_by:
            self.published_by = published_by
        self.save(update_fields=["is_published", "published_at", "published_by", "updated_at"])

    def unpublish(self) -> None:
        if not self.is_published:
            return
        self.is_published = False
        self.save(update_fields=["is_published", "updated_at"])


# ===========================================================================
# Lesson
# ===========================================================================

class Lesson(OrderedModel):
    """
    A single learning unit within a Module.

    Access control flags:
      is_free_preview   → Guests can access (authenticated or not)
      is_student_only   → Only STUDENT role and above (no guests)
      (neither flag)    → All authenticated users (guest + student)

    For QUIZ lessons: questions are linked via LessonQuestion.
    For ROAD_SIGN lessons: road_sign FK links to the RoadSign reference.
    For VIDEO lessons: use media_url for embeds (YouTube) or media_file for upload.
    """

    module = models.ForeignKey(
        Module,
        on_delete=models.CASCADE,
        related_name="lessons",
        verbose_name=_("Module"),
    )
    title = models.CharField(_("Title"), max_length=200)
    lesson_type = models.CharField(
        _("Lesson Type"),
        max_length=20,
        choices=LessonType.choices,
        default=LessonType.TEXT,
        db_index=True,
    )

    # ── Content payload (filled based on lesson_type) ────────────────────────
    content_text = models.TextField(
        _("Text Content"),
        blank=True,
        help_text=_("Markdown/HTML body. Used for TEXT lessons and as quiz intro."),
    )
    media_file = models.FileField(
        _("Media File"),
        upload_to="lms/lessons/media/%Y/%m/",
        null=True,
        blank=True,
        help_text=_("Audio (MP3) or Video (MP4) file upload."),
    )
    media_url = models.URLField(
        _("Media URL"),
        blank=True,
        help_text=_("External video URL (YouTube embed, etc.) for VIDEO lessons."),
    )
    road_sign = models.ForeignKey(
        RoadSign,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lessons",
        verbose_name=_("Road Sign"),
        help_text=_("Primary road sign featured in a ROAD_SIGN lesson."),
    )
    duration_minutes = models.PositiveSmallIntegerField(_("Duration (minutes)"), default=0)

    # ── Access control flags ─────────────────────────────────────────────────
    is_free_preview = models.BooleanField(
        _("Free Preview"),
        default=False,
        db_index=True,
        help_text=_(
            "If True, this lesson is visible to everyone including guests. "
            "Use for sample/intro lessons."
        ),
    )
    is_student_only = models.BooleanField(
        _("Student Only"),
        default=False,
        db_index=True,
        help_text=_(
            "If True, only enrolled students (and staff) can access this lesson. "
            "Guests are blocked even if they are authenticated."
        ),
    )

    class Meta(OrderedModel.Meta):
        verbose_name = _("Lesson")
        verbose_name_plural = _("Lessons")

    def __str__(self) -> str:
        flags = ""
        if self.is_free_preview:
            flags += "👁 "
        if self.is_student_only:
            flags += "🎓 "
        return f"{flags}{self.module.course.title} › {self.module.title} › {self.title}"

    @property
    def question_count(self) -> int:
        """Number of quiz questions attached to this lesson (QUIZ type only)."""
        return self.lesson_questions.filter(question__is_active=True).count()

    def can_access(self, user) -> bool:
        """
        Inline access check. Use ContentGateService.can_access_lesson()
        for the full service-layer check with logging.
        """
        if self.is_free_preview:
            return True
        if not (user and user.is_authenticated):
            return False
        from apps.accounts.constants import UserRole
        if user.role in (
            UserRole.SYSTEM_ADMIN, UserRole.TRAINING_ADMIN,
            UserRole.TUTOR, UserRole.BOARD_REVIEWER,
        ):
            return True
        if self.is_student_only:
            return user.role == UserRole.STUDENT
        return True  # Authenticated guest or student


# ===========================================================================
# Lesson ↔ QuizQuestion join table
# ===========================================================================

class LessonQuestion(OrderedModel):
    """
    Links QuizQuestions to QUIZ-type Lessons.
    Ordered so tutors can control the question sequence within a quiz lesson.
    """

    lesson = models.ForeignKey(
        Lesson,
        on_delete=models.CASCADE,
        related_name="lesson_questions",
        verbose_name=_("Lesson"),
    )
    question = models.ForeignKey(
        "lms.QuizQuestion",
        on_delete=models.CASCADE,
        related_name="lesson_associations",
        verbose_name=_("Question"),
    )

    class Meta(OrderedModel.Meta):
        verbose_name = _("Lesson Question")
        verbose_name_plural = _("Lesson Questions")
        unique_together = [["lesson", "question"]]

    def __str__(self) -> str:
        return f"{self.lesson.title} — Q{self.sort_order}"
