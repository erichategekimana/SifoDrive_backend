"""
apps/examinations/models/exam.py
================================
Dedicated Exam definition model completely independent of LMS quizzes.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _
from apps.core.models import BaseModel
from apps.examinations.models.choices import ExamType, ExamStatus


class Exam(BaseModel):
    """
    Official theory examination window.
    Completely distinct entity from LMS quizzes or activities.

    Fixed System Engine Constants:
      - Total Questions: 20
      - Duration: 20 minutes exact
      - Points per Question: 1
      - Passing Score: 12
      - Domain distribution: Priority 4, Signage 4, Speed 4, Legal 3, Safety 3, Parking 2
    """
    title = models.CharField(_("Exam Title (English)"), max_length=255)
    title_kinyarwanda = models.CharField(_("Exam Title (Kinyarwanda)"), max_length=255, blank=True, default="")
    title_french = models.CharField(_("Exam Title (French)"), max_length=255, blank=True, default="")

    exam_type = models.CharField(
        _("Exam Type"),
        max_length=20,
        choices=ExamType.choices,
        default=ExamType.STUDENT,
        db_index=True,
    )
    status = models.CharField(
        _("Status"),
        max_length=20,
        choices=ExamStatus.choices,
        default=ExamStatus.DRAFT,
        db_index=True,
    )

    cohort = models.ForeignKey(
        "live_classes.Cohort",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="official_exams",
        verbose_name=_("Target Cohort"),
        help_text=_("The enrolled student cohort eligible to sit for this official exam."),
    )

    open_date = models.DateTimeField(_("Open Date"), null=True, blank=True)
    due_date = models.DateTimeField(_("Due Date"), null=True, blank=True)
    closing_date = models.DateTimeField(
        _("Closing Date"),
        null=True,
        blank=True,
        help_text=_("Strict cutoff after which no student exam attempts may be initiated."),
    )

    instructions = models.TextField(_("Candidate Instructions (English)"), blank=True, default="")
    instructions_kinyarwanda = models.TextField(_("Candidate Instructions (Kinyarwanda)"), blank=True, default="")
    instructions_french = models.TextField(_("Candidate Instructions (French)"), blank=True, default="")

    rubric = models.TextField(_("Grading Rubric & Rules (English)"), blank=True, default="")
    rubric_kinyarwanda = models.TextField(_("Grading Rubric & Rules (Kinyarwanda)"), blank=True, default="")
    rubric_french = models.TextField(_("Grading Rubric & Rules (French)"), blank=True, default="")

    is_published = models.BooleanField(_("Is Published"), default=False, db_index=True)
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_exams",
        verbose_name=_("Created By"),
    )

    # Fixed Engine Rules (Read-Only Properties)
    TOTAL_QUESTIONS = 20
    DURATION_MINUTES = 20
    POINTS_PER_QUESTION = 1
    PASSING_SCORE = 12

    class Meta(BaseModel.Meta):
        app_label = "examinations"
        verbose_name = _("Examination")
        verbose_name_plural = _("Examinations")
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.exam_type}] {self.title} ({self.status})"
