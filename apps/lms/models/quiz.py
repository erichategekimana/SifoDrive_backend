"""
apps/lms/models/quiz.py
========================
Quiz, QuizQuestion (bank), and QuizQuestionItem models.

QuizQuestion  → the global question bank, used in both lesson quizzes and exams.
Quiz          → a structured assessment linked to a Course/Module.
QuizQuestionItem → an individual question slot within a Quiz (can reference the bank or be scratch).
"""

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel, OrderedModel
from apps.lms.models.choices import CorrectOption, Difficulty, QuizDomain
from apps.lms.models.content import Module, RoadSign
from apps.lms.models.curriculum import Course


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

    question_number = models.PositiveIntegerField(
        _("Question Number"),
        null=True,
        blank=True,
        db_index=True,
        help_text=_("Official Rwanda Highway Code question reference number (1-433)."),
    )
    domain = models.CharField(
        _("Domain"), max_length=20, choices=QuizDomain.choices, db_index=True
    )
    difficulty = models.CharField(
        _("Difficulty"),
        max_length=10,
        choices=Difficulty.choices,
        default=Difficulty.MEDIUM,
        db_index=True,
    )
    question_text = models.TextField(_("Question (English)"), blank=True)
    question_text_kinyarwanda = models.TextField(_("Question (Kinyarwanda)"), blank=True)

    option_a = models.CharField(_("Option A (English)"), max_length=500, blank=True)
    option_b = models.CharField(_("Option B (English)"), max_length=500, blank=True)
    option_c = models.CharField(_("Option C (English)"), max_length=500, blank=True)
    option_d = models.CharField(_("Option D (English)"), max_length=500, blank=True)
    option_a_kinyarwanda = models.CharField(_("Option A (Kinyarwanda)"), max_length=500, blank=True)
    option_b_kinyarwanda = models.CharField(_("Option B (Kinyarwanda)"), max_length=500, blank=True)
    option_c_kinyarwanda = models.CharField(_("Option C (Kinyarwanda)"), max_length=500, blank=True)
    option_d_kinyarwanda = models.CharField(_("Option D (Kinyarwanda)"), max_length=500, blank=True)

    correct_option = models.CharField(
        _("Correct Option"), max_length=1, choices=CorrectOption.choices
    )
    explanation = models.TextField(
        _("Explanation (English)"),
        blank=True,
        help_text=_("Shown after the student answers. Explains why the answer is correct."),
    )
    explanation_kinyarwanda = models.TextField(
        _("Explanation (Kinyarwanda)"),
        blank=True,
        help_text=_("Ibisobanuro mu Kinyarwanda by'impamvu igisubizo ari cyo cy'ukuri."),
    )
    image = models.ImageField(
        _("Diagram / Image"),
        upload_to="lms/questions/images/",
        null=True,
        blank=True,
        help_text=_("Road sign or intersection diagram associated with this question prompt."),
    )
    option_a_image = models.ImageField(
        _("Option A Image"), upload_to="lms/questions/options/", null=True, blank=True,
        help_text=_("Image diagram for Option A if this question uses image-based choices."),
    )
    option_b_image = models.ImageField(
        _("Option B Image"), upload_to="lms/questions/options/", null=True, blank=True,
        help_text=_("Image diagram for Option B if this question uses image-based choices."),
    )
    option_c_image = models.ImageField(
        _("Option C Image"), upload_to="lms/questions/options/", null=True, blank=True,
        help_text=_("Image diagram for Option C if this question uses image-based choices."),
    )
    option_d_image = models.ImageField(
        _("Option D Image"), upload_to="lms/questions/options/", null=True, blank=True,
        help_text=_("Image diagram for Option D if this question uses image-based choices."),
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
# Quiz (Course Assessment Engine)
# ===========================================================================

class Quiz(BaseModel):
    """
    Comprehensive structured quiz linked to a Course or specific Module.
    Authored and managed by Training Admins and System Admins.
    Features open dates, deadlines, rubrics, passing thresholds, and question items.
    """

    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name="quizzes", verbose_name=_("Course")
    )
    module = models.ForeignKey(
        Module,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="quizzes",
        verbose_name=_("Module"),
        help_text=_("Optional: link quiz directly to a specific module within the course."),
    )
    title = models.CharField(_("Title (English)"), max_length=200)
    title_kinyarwanda = models.CharField(
        _("Title (Kinyarwanda)"), max_length=200, blank=True, default=""
    )
    description = models.TextField(_("Description (English)"), blank=True, default="")
    description_kinyarwanda = models.TextField(
        _("Description (Kinyarwanda)"), blank=True, default=""
    )
    open_date = models.DateTimeField(
        _("Open Date"),
        null=True,
        blank=True,
        help_text=_(
            "When the quiz unlocks for students. If published but open_date is in future, "
            "quiz remains scheduled."
        ),
    )
    deadline = models.DateTimeField(
        _("Deadline / Due Date"),
        null=True,
        blank=True,
        help_text=_("When the quiz closes. Submissions after this date are blocked."),
    )
    time_limit_minutes = models.PositiveSmallIntegerField(
        _("Time Limit (minutes)"), default=0, help_text=_("0 indicates no time limit.")
    )
    total_score = models.PositiveIntegerField(
        _("Total Score / Points"),
        default=100,
        help_text=_("Total maximum achievable points for this quiz."),
    )
    passing_score = models.PositiveIntegerField(
        _("Passing Score (%)"), default=70, help_text=_("Passing threshold percentage (e.g. 70%).")
    )
    rubric = models.TextField(
        _("Grading Rubric & Guidelines (English)"), blank=True, default="",
        help_text=_("Comprehensive grading rubric, evaluation criteria, and instructions for students."),
    )
    rubric_kinyarwanda = models.TextField(
        _("Grading Rubric & Guidelines (Kinyarwanda)"), blank=True, default=""
    )
    max_attempts = models.PositiveSmallIntegerField(
        _("Maximum Attempts"),
        default=1,
        help_text=_("Number of attempts permitted (0 for unlimited)."),
    )
    shuffle_questions = models.BooleanField(_("Shuffle Questions"), default=False)
    is_published = models.BooleanField(_("Published"), default=False, db_index=True)
    allow_tutor_scheduling = models.BooleanField(
        _("Allow Tutor Scheduling"),
        default=True,
        help_text=_(
            "If True, tutors can independently schedule open dates, deadlines, and extensions per cohort. "
            "If False, follows global training admin schedule."
        ),
    )
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_quizzes",
        verbose_name=_("Created By"),
    )

    class Meta(BaseModel.Meta):
        verbose_name = _("Quiz")
        verbose_name_plural = _("Quizzes")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.title} ({self.course.title})"

    @property
    def question_count(self) -> int:
        return self.items.count()

    @property
    def calculated_total_points(self) -> int:
        total = self.items.aggregate(total=models.Sum("points"))["total"]
        return total if total is not None else self.total_score

    @property
    def status(self) -> str:
        """
        Dynamic status:
        - 'DRAFT' if not published
        - 'SCHEDULED' if published but open_date is in the future
        - 'CLOSED' if deadline passed
        - 'OPEN' if published and within window
        """
        if not self.is_published:
            return "DRAFT"
        now = timezone.now()
        if self.open_date and self.open_date > now:
            return "SCHEDULED"
        if self.deadline and self.deadline < now:
            return "CLOSED"
        return "OPEN"


# ===========================================================================
# QuizQuestionItem (individual slot within a Quiz)
# ===========================================================================

class QuizQuestionItem(OrderedModel):
    """
    An individual question in a Quiz.
    Can be pulled from the central QuizQuestion bank (original_question FK) with customizations,
    or authored completely from scratch (original_question = None).
    """

    quiz = models.ForeignKey(
        Quiz, on_delete=models.CASCADE, related_name="items", verbose_name=_("Quiz")
    )
    original_question = models.ForeignKey(
        QuizQuestion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="quiz_instances",
        verbose_name=_("Source Bank Question"),
        help_text=_("Reference to the bank question this was pulled from, if any."),
    )
    points = models.PositiveSmallIntegerField(_("Points / Weight"), default=1)
    question_text = models.TextField(_("Question (English)"))
    question_text_kinyarwanda = models.TextField(
        _("Question (Kinyarwanda)"), blank=True, default=""
    )
    option_a = models.CharField(_("Option A (English)"), max_length=500)
    option_b = models.CharField(_("Option B (English)"), max_length=500)
    option_c = models.CharField(_("Option C (English)"), max_length=500, blank=True, default="")
    option_d = models.CharField(_("Option D (English)"), max_length=500, blank=True, default="")
    option_a_kinyarwanda = models.CharField(_("Option A (Kinyarwanda)"), max_length=500, blank=True, default="")
    option_b_kinyarwanda = models.CharField(_("Option B (Kinyarwanda)"), max_length=500, blank=True, default="")
    option_c_kinyarwanda = models.CharField(_("Option C (Kinyarwanda)"), max_length=500, blank=True, default="")
    option_d_kinyarwanda = models.CharField(_("Option D (Kinyarwanda)"), max_length=500, blank=True, default="")
    correct_option = models.CharField(
        _("Correct Option"), max_length=1, choices=CorrectOption.choices, default=CorrectOption.A
    )
    explanation = models.TextField(_("Explanation (English)"), blank=True, default="")
    explanation_kinyarwanda = models.TextField(
        _("Explanation (Kinyarwanda)"), blank=True, default=""
    )
    domain = models.CharField(
        _("Domain"),
        max_length=20,
        choices=QuizDomain.choices,
        default=QuizDomain.PRIORITY,
        db_index=True,
    )
    difficulty = models.CharField(
        _("Difficulty"),
        max_length=10,
        choices=Difficulty.choices,
        default=Difficulty.MEDIUM,
        db_index=True,
    )

    class Meta(OrderedModel.Meta):
        verbose_name = _("Quiz Question Item")
        verbose_name_plural = _("Quiz Question Items")

    def __str__(self) -> str:
        return f"{self.quiz.title} - Q{self.sort_order}: {self.question_text[:60]}"
