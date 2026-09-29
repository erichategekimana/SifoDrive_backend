"""
apps/lms/models/progress.py
============================
StudentProgress and LessonBookmark models.

These track learner engagement with content:
  StudentProgress   → one record per (student, lesson) pair
  LessonBookmark    → students can bookmark lessons for later review
"""

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel
from apps.lms.models.content import Lesson


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
    is_completed = models.BooleanField(_("Completed"), default=False, db_index=True)
    completed_at = models.DateTimeField(_("Completed At"), null=True, blank=True)
    time_spent_seconds = models.PositiveIntegerField(_("Time Spent (seconds)"), default=0)

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
        self.save(update_fields=["is_completed", "completed_at", "time_spent_seconds", "updated_at"])

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
