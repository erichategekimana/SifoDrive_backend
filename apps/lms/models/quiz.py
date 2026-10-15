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
from apps.lms.models.choices import CorrectOption, Difficulty, QuizDomain, QuizType
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
    quiz_type = models.CharField(
        _("Quiz Type"),
        max_length=20,
        choices=QuizType.choices,
        default=QuizType.LIVE_TIMED,
        db_index=True,
        help_text=_(
            "LIVE_TIMED: Live attempt with timer, attempts, and tab proctoring. "
            "WORK_SUBMISSION: Self-paced assignment where student submits their work/answers."
        ),
    )
    enable_proctoring = models.BooleanField(
        _("Enable Tab Proctoring"),
        default=True,
        help_text=_("Tracks tab switches and window blur incidents during live quiz."),
    )
    max_tab_switches_allowed = models.PositiveSmallIntegerField(
        _("Max Tab Switches Allowed"),
        default=3,
        help_text=_("Number of tab switch warnings before flagging or auto-submitting."),
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
        help_text=_("Standard due date. Submissions after this date are flagged as late if allowed."),
    )
    closing_date = models.DateTimeField(
        _("Closing Date / Cutoff"),
        null=True,
        blank=True,
        help_text=_(
            "Final cutoff date after which no submissions are accepted, even if late submissions are enabled."
        ),
    )
    allow_late_submission = models.BooleanField(
        _("Allow Late Submission"),
        default=False,
        help_text=_(
            "If True, students can submit past the deadline up to closing_date. "
            "Late submissions are flagged as late with the number of days late. "
            "Never allowed for final exams."
        ),
    )
    is_final_exam = models.BooleanField(
        _("Is Final Exam"),
        default=False,
        db_index=True,
        help_text=_(
            "Designates this assessment as a School Theory Final Exam. "
            "Final exams enforce strict deadline cutoff with no late submissions allowed."
        ),
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
    release_grades_immediately = models.BooleanField(
        _("Release Grades Immediately"),
        default=False,
        help_text=_(
            "If True, students view their scores and results immediately upon completion. "
            "If False (default), tutor must manually publish grades."
        ),
    )
    allow_tutor_scheduling = models.BooleanField(
        _("Allow Tutor Scheduling"),
        default=True,
        help_text=_(
            "If True, tutors can independently schedule open dates, deadlines, and extensions per cohort. "
            "If False, follows global training admin schedule."
        ),
    )
    allow_tutor_edit_instructions = models.BooleanField(
        _("Allow Tutor Edit Instructions"),
        default=True,
        help_text=_(
            "If True, tutors can customize instructions, rubric guidelines, and advice for their assigned cohort."
        ),
    )
    allow_tutor_edit_duration = models.BooleanField(
        _("Allow Tutor Edit Duration"),
        default=True,
        help_text=_(
            "If True, tutors can adjust the time limit (duration) for their assigned cohort."
        ),
    )
    allow_tutor_edit_attempts = models.BooleanField(
        _("Allow Tutor Edit Attempts"),
        default=True,
        help_text=_(
            "If True, tutors can configure the maximum attempts allowed for their assigned cohort."
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
        - 'CLOSED' if cutoff passed (closing_date or deadline)
        - 'OPEN' if published and within submission window
        """
        if not self.is_published:
            return "DRAFT"
        now = timezone.now()
        if self.open_date and self.open_date > now:
            return "SCHEDULED"
        effective_close = self.closing_date if (self.allow_late_submission and not self.is_final_exam and self.closing_date) else self.deadline
        if effective_close and effective_close < now:
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


# ===========================================================================
# QuizSubmission (Student Live Attempt & Work Submission Lifecycle)
# ===========================================================================

class QuizSubmission(BaseModel):
    """
    Records student attempt lifecycle for both Quiz types:
    - LIVE_TIMED: Captures live countdown duration, score, and proctoring tab-switch telemetry.
    - WORK_SUBMISSION: Captures student work text, attached files, answers, and rubric grading.
    """

    quiz = models.ForeignKey(
        Quiz, on_delete=models.CASCADE, related_name="submissions", verbose_name=_("Quiz")
    )
    student = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="quiz_submissions",
        verbose_name=_("Student"),
    )
    cohort = models.ForeignKey(
        "live_classes.Cohort",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="quiz_submissions",
        verbose_name=_("Cohort"),
    )
    attempt_number = models.PositiveSmallIntegerField(_("Attempt Number"), default=1)
    quiz_type = models.CharField(
        _("Quiz Type"),
        max_length=20,
        choices=QuizType.choices,
        default=QuizType.LIVE_TIMED,
    )
    score = models.PositiveIntegerField(_("Score / Achieved Points"), default=0)
    total_score = models.PositiveIntegerField(_("Total Points Possible"), default=100)
    percentage = models.FloatField(_("Percentage (0-100)"), default=0.0)
    is_passed = models.BooleanField(_("Passed Threshold"), default=False)

    # Student submission payloads
    student_answers = models.JSONField(
        _("Student Answers"),
        default=dict,
        blank=True,
        help_text=_("Mapping of question item id -> selected option or written response."),
    )
    work_submission_text = models.TextField(
        _("Work Submission Body / Notes"),
        blank=True,
        default="",
        help_text=_("Detailed submission text for WORK_SUBMISSION take-home quizzes."),
    )
    work_submission_file = models.FileField(
        _("Work Submission File"),
        upload_to="lms/quiz_submissions/",
        null=True,
        blank=True,
        help_text=_("Optional attachment uploaded by the student."),
    )

    # Telemetry and Simple Proctoring
    time_spent_seconds = models.PositiveIntegerField(_("Time Spent (seconds)"), default=0)
    tab_switch_count = models.PositiveSmallIntegerField(
        _("Tab Switch Count"),
        default=0,
        help_text=_("Number of times the student switched tabs or navigated away during live exam."),
    )
    proctoring_violations = models.JSONField(
        _("Proctoring Violations Log"),
        default=list,
        blank=True,
        help_text=_("Chronological log of tab blur/hide events recorded during the live attempt."),
    )
    is_flagged = models.BooleanField(
        _("Flagged for Suspicious Activity"),
        default=False,
        help_text=_("Set True if tab switch count exceeded the allowed proctoring threshold."),
    )
    flagged_questions = models.JSONField(
        _("Flagged Questions for Review"),
        default=list,
        blank=True,
        help_text=_("List of question IDs flagged by student for review during quiz."),
    )

    feedback = models.TextField(_("Tutor / Grader Feedback"), blank=True, default="")
    is_auto_graded = models.BooleanField(
        _("Is Auto Graded"),
        default=True,
        help_text=_("Indicates whether this attempt was automatically scored by the quiz engine."),
    )
    auto_score = models.PositiveIntegerField(
        _("Original Auto Score"),
        null=True,
        blank=True,
        help_text=_("The initial auto-graded score before any tutor adjustments."),
    )
    is_grade_overridden = models.BooleanField(
        _("Grade Overridden"),
        default=False,
        db_index=True,
        help_text=_("True if a tutor or administrator manually edited the auto-calculated grade."),
    )
    grade_overridden_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="overridden_quiz_submissions",
        verbose_name=_("Grade Overridden By"),
        help_text=_("Staff member or tutor who overrode the auto-grade."),
    )
    grade_overridden_at = models.DateTimeField(
        _("Grade Overridden At"),
        null=True,
        blank=True,
    )
    grade_override_reason = models.TextField(
        _("Grade Override Reason"),
        blank=True,
        default="",
    )
    graded_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="graded_quiz_submissions",
        verbose_name=_("Graded By"),
    )
    graded_at = models.DateTimeField(_("Graded At"), null=True, blank=True)

    class Meta(BaseModel.Meta):
        verbose_name = _("Quiz Submission")
        verbose_name_plural = _("Quiz Submissions")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.student.phone_number} - {self.quiz.title} (Attempt #{self.attempt_number})"

