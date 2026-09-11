"""
apps/lms/models.py
===================
Learning Management System domain models.

Architecture:
  Course  ──< Module ──< Lesson
  RoadSign ← referenced by Lesson (ROAD_SIGN type) and QuizQuestion
  QuizQuestion ── linked to Lesson (QUIZ type) via LessonQuestion
  StudentProgress — one record per (student, lesson)
  LessonBookmark  — students can bookmark lessons for later

Publish lifecycle:
  Course    → has is_published / publish() / unpublish()
  Module    → has is_published / publish() / unpublish()
  Lesson    → visible when its parent Module AND Course are published

Access control (enforced in services + views):
  ┌──────────────────────────┬───────┬─────────┬───────┬───────┐
  │ Content                  │ Guest │ Student │ Tutor │ Admin │
  ├──────────────────────────┼───────┼─────────┼───────┼───────┤
  │ Published course list    │  ✓    │   ✓     │  ✓    │  ✓   │
  │ Draft course list        │  ✗    │   ✗     │  ✓    │  ✓   │
  │ Free-preview lessons     │  ✓    │   ✓     │  ✓    │  ✓   │
  │ Standard lessons         │  ✓    │   ✓     │  ✓    │  ✓   │
  │ Student-only lessons     │  ✗    │   ✓     │  ✓    │  ✓   │
  │ Road signs (reference)   │  ✓    │   ✓     │  ✓    │  ✓   │
  │ Quiz questions           │  ✗    │   ✓     │  ✓    │  ✓   │
  │ Create / edit content    │  ✗    │   ✗     │  ✓    │  ✓   │
  │ Publish content          │  ✗    │   ✗     │  ✗    │  ✓   │
  └──────────────────────────┴───────┴─────────┴───────┴───────┘

No license_category on Course — all content is universal driving theory.
"""

import uuid

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel, OrderedModel


# ===========================================================================
# Choices / Enumerations
# ===========================================================================

class LessonType(models.TextChoices):
    TEXT       = "TEXT",      _("Text Article")
    AUDIO      = "AUDIO",     _("Audio Lesson")
    VIDEO      = "VIDEO",     _("Video Lesson")
    ROAD_SIGN  = "ROAD_SIGN", _("Road Sign Study")
    QUIZ       = "QUIZ",      _("Interactive Quiz")


class RoadSignCategory(models.TextChoices):
    WARNING     = "WARNING",     _("Warning Signs (Yellow/Triangle)")
    PROHIBITORY = "PROHIBITORY", _("Prohibitory Signs (Red/Circle)")
    MANDATORY   = "MANDATORY",   _("Mandatory Signs (Blue/Circle)")
    INFORMATORY = "INFORMATORY", _("Informatory Signs (Blue/Rectangle)")
    ROAD_MARKING = "ROAD_MARKING", _("Road Markings")


class QuizDomain(models.TextChoices):
    PRIORITY = "PRIORITY", _("Priority Rules & Intersections")
    SIGNAGE  = "SIGNAGE",  _("Traffic Signage & Road Markings")
    SPEED    = "SPEED",    _("Speed Limits & Overtaking")
    LEGAL    = "LEGAL",    _("Legal Framework & Penalties")
    SAFETY   = "SAFETY",   _("Vehicle Safety & First Aid")
    PARKING  = "PARKING",  _("Parking & Stopping Rules")


class Difficulty(models.TextChoices):
    EASY   = "EASY",   _("Easy")
    MEDIUM = "MEDIUM", _("Medium")
    HARD   = "HARD",   _("Hard")


class CorrectOption(models.TextChoices):
    A = "A", "A"
    B = "B", "B"
    C = "C", "C"
    D = "D", "D"


# ===========================================================================
# Course
# ===========================================================================

class Course(OrderedModel):
    """
    Top-level learning container — a complete curriculum on driving theory.
    No license_category: all courses cover universal Rwanda driving rules.

    Publish lifecycle:
      - is_published=False → draft, hidden from students & guests
      - is_published=True  → live, accessible to all authorised learners
      - Only SYSTEM_ADMIN can call publish(); Tutors create drafts.
    """

    title = models.CharField(
        _("Title"),
        max_length=200,
    )
    description = models.TextField(
        _("Description"),
        blank=True,
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
    is_published = models.BooleanField(
        _("Published"),
        default=False,
        db_index=True,
    )
    published_at = models.DateTimeField(
        _("Published At"),
        null=True,
        blank=True,
    )
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
        """Make this course live. Idempotent."""
        if self.is_published:
            return
        self.is_published = True
        self.published_at = timezone.now()
        if published_by:
            self.published_by = published_by
        self.save(update_fields=[
            "is_published", "published_at", "published_by", "updated_at"
        ])

    def unpublish(self) -> None:
        """Pull course back to draft state. Idempotent."""
        if not self.is_published:
            return
        self.is_published = False
        self.save(update_fields=["is_published", "updated_at"])


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
    title = models.CharField(
        _("Title"),
        max_length=200,
    )
    description = models.TextField(
        _("Description"),
        blank=True,
    )
    is_foundational = models.BooleanField(
        _("Foundational"),
        default=False,
        db_index=True,
        help_text=_(
            "Foundational modules must be 100% complete before a student "
            "is eligible to sit the driving theory exam."
        ),
    )

    # ── Publish lifecycle ────────────────────────────────────────────────────
    is_published = models.BooleanField(
        _("Published"),
        default=False,
        db_index=True,
    )
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
        self.save(update_fields=[
            "is_published", "published_at", "published_by", "updated_at"
        ])

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
    title = models.CharField(
        _("Title"),
        max_length=200,
    )
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
        "lms.RoadSign",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lessons",
        verbose_name=_("Road Sign"),
        help_text=_("Primary road sign featured in a ROAD_SIGN lesson."),
    )
    duration_minutes = models.PositiveSmallIntegerField(
        _("Duration (minutes)"),
        default=0,
    )

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
        return self.lesson_questions.filter(
            question__is_active=True
        ).count()

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
        if user.role in (UserRole.SYSTEM_ADMIN, UserRole.TRAINING_ADMIN, UserRole.TUTOR, UserRole.BOARD_REVIEWER):
            return True
        if self.is_student_only:
            return user.role == UserRole.STUDENT
        return True  # Authenticated guest or student


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

    name = models.CharField(
        _("Sign Name"),
        max_length=200,
    )
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
    image = models.ImageField(
        _("Sign Image"),
        upload_to="lms/road_signs/",
    )
    description = models.TextField(
        _("Description (English)"),
    )
    description_kinyarwanda = models.TextField(
        _("Description (Kinyarwanda)"),
        blank=True,
    )
    is_active = models.BooleanField(
        _("Active"),
        default=True,
        db_index=True,
    )

    class Meta(BaseModel.Meta):
        verbose_name = _("Road Sign")
        verbose_name_plural = _("Road Signs")
        ordering = ["category", "name"]

    def __str__(self) -> str:
        code = f" ({self.sign_code})" if self.sign_code else ""
        return f"{self.name}{code} — {self.get_category_display()}"


# ===========================================================================
# Quiz Question Bank
# ===========================================================================

class QuizQuestion(BaseModel):
    """
    Multiple-choice question used in:
      1. Lesson quizzes (via LessonQuestion join table)
      2. Examination engine (separate sampling by domain)

    Accessible to STUDENT, TUTOR, and SYSTEM_ADMIN only.
    Guests cannot access quiz questions.
    """

    domain = models.CharField(
        _("Domain"),
        max_length=20,
        choices=QuizDomain.choices,
        db_index=True,
    )
    difficulty = models.CharField(
        _("Difficulty"),
        max_length=10,
        choices=Difficulty.choices,
        default=Difficulty.MEDIUM,
        db_index=True,
    )
    question_text = models.TextField(
        _("Question (English)"),
    )
    question_text_kinyarwanda = models.TextField(
        _("Question (Kinyarwanda)"),
        blank=True,
    )
    option_a = models.CharField(_("Option A"), max_length=500)
    option_b = models.CharField(_("Option B"), max_length=500)
    option_c = models.CharField(_("Option C"), max_length=500)
    option_d = models.CharField(_("Option D"), max_length=500)
    correct_option = models.CharField(
        _("Correct Option"),
        max_length=1,
        choices=CorrectOption.choices,
    )
    explanation = models.TextField(
        _("Explanation"),
        blank=True,
        help_text=_("Shown after the student answers. Explains why the answer is correct."),
    )
    road_sign = models.ForeignKey(
        RoadSign,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="questions",
        verbose_name=_("Related Road Sign"),
        help_text=_("Optional: if this question is about a specific road sign."),
    )
    is_active = models.BooleanField(
        _("Active"),
        default=True,
        db_index=True,
        help_text=_("Inactive questions are excluded from exams and lesson quizzes."),
    )
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_questions",
        verbose_name=_("Created By"),
    )

    class Meta(BaseModel.Meta):
        verbose_name = _("Quiz Question")
        verbose_name_plural = _("Quiz Questions")
        ordering = ["domain", "difficulty"]

    def __str__(self) -> str:
        return f"[{self.domain}/{self.difficulty}] {self.question_text[:80]}…"

    @property
    def correct_text(self) -> str:
        """Return the text of the correct option for display."""
        return getattr(self, f"option_{self.correct_option.lower()}", "")


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
        QuizQuestion,
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


# ===========================================================================
# Student Progress
# ===========================================================================

class StudentProgress(BaseModel):
    """
    Tracks a student's completion of each lesson.
    One record per (student, lesson) pair — enforced via unique_together.

    For QUIZ lessons:
      - is_completed is set True when the quiz is submitted.
      - quiz_score stores the percentage (0–100).
      - quiz_attempts counts how many times the student retook the quiz.

    The ProgressService uses this table to compute:
      - Foundational module completion rate (exam eligibility)
      - Overall course completion percentage (dashboard)
    """

    student = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="lesson_progress",
        verbose_name=_("Student"),
        db_index=True,
    )
    lesson = models.ForeignKey(
        Lesson,
        on_delete=models.CASCADE,
        related_name="student_progress",
        verbose_name=_("Lesson"),
    )
    is_completed = models.BooleanField(
        _("Completed"),
        default=False,
        db_index=True,
    )
    completed_at = models.DateTimeField(
        _("Completed At"),
        null=True,
        blank=True,
    )
    time_spent_seconds = models.PositiveIntegerField(
        _("Time Spent (seconds)"),
        default=0,
    )

    # ── Quiz-specific fields ─────────────────────────────────────────────────
    quiz_score = models.PositiveSmallIntegerField(
        _("Quiz Score (%)"),
        null=True,
        blank=True,
        help_text=_("Percentage score (0–100) for QUIZ type lessons."),
    )
    quiz_attempts = models.PositiveSmallIntegerField(
        _("Quiz Attempts"),
        default=0,
        help_text=_("Number of times the student has attempted this quiz."),
    )

    class Meta(BaseModel.Meta):
        verbose_name = _("Student Progress")
        verbose_name_plural = _("Student Progress Records")
        unique_together = [["student", "lesson"]]
        indexes = [
            models.Index(fields=["student", "is_completed"]),
        ]

    def __str__(self) -> str:
        status = "✓" if self.is_completed else "○"
        return f"[{status}] {self.student.phone_number[-4:]} — {self.lesson.title}"

    def mark_complete(self, time_spent: int = 0) -> None:
        """Mark this lesson as completed. Idempotent."""
        if self.is_completed:
            return
        self.is_completed = True
        self.completed_at = timezone.now()
        if time_spent:
            self.time_spent_seconds = time_spent
        self.save(update_fields=[
            "is_completed", "completed_at", "time_spent_seconds", "updated_at"
        ])

    def record_quiz_attempt(self, score: int, time_spent: int = 0) -> None:
        """Record a quiz attempt. Updates score if improved."""
        self.quiz_attempts += 1
        # Keep best score across attempts
        if self.quiz_score is None or score > self.quiz_score:
            self.quiz_score = score
        if time_spent:
            self.time_spent_seconds += time_spent
        if score >= 70:  # Pass threshold
            self.mark_complete(time_spent=0)
        self.save(update_fields=[
            "quiz_attempts", "quiz_score", "time_spent_seconds",
            "is_completed", "completed_at", "updated_at",
        ])


# ===========================================================================
# Lesson Bookmark
# ===========================================================================

class LessonBookmark(BaseModel):
    """
    Allows students to bookmark lessons for quick access.
    One bookmark per (student, lesson) — enforced via unique_together.
    """

    student = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="bookmarks",
        verbose_name=_("Student"),
    )
    lesson = models.ForeignKey(
        Lesson,
        on_delete=models.CASCADE,
        related_name="bookmarks",
        verbose_name=_("Lesson"),
    )
    note = models.CharField(
        _("Note"),
        max_length=500,
        blank=True,
        help_text=_("Optional personal note about this lesson."),
    )

    class Meta(BaseModel.Meta):
        verbose_name = _("Lesson Bookmark")
        verbose_name_plural = _("Lesson Bookmarks")
        unique_together = [["student", "lesson"]]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.student.phone_number[-4:]} bookmarked '{self.lesson.title}'"
