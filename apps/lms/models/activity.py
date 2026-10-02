"""
apps/lms/models/activity.py
===========================
Tutor cohort activities, assignments, practical drills, and student submissions.
"""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class ActivityType(models.TextChoices):
    ASSIGNMENT = "ASSIGNMENT", _("Assignment / Homework")
    PRACTICAL_DRILL = "PRACTICAL_DRILL", _("Practical Driving / Vehicle Drill")
    CASE_STUDY = "CASE_STUDY", _("Traffic Situation Case Study")
    DISCUSSION = "DISCUSSION", _("Group Discussion Topic")
    READING_EXERCISE = "READING_EXERCISE", _("Highway Code Reading Task")


class ActivitySubmissionType(models.TextChoices):
    FILE_UPLOAD = "FILE_UPLOAD", _("File Upload (PDF / Image)")
    TEXT_RESPONSE = "TEXT_RESPONSE", _("Written Online Response")
    PRACTICAL_EVALUATION = "PRACTICAL_EVALUATION", _("Evaluated In-Person / Live Session")
    NONE = "NONE", _("No Submission Required")


class CohortActivity(BaseModel):
    """
    Learning activity authored by a tutor for a specific cohort.
    Enables homework assignments, practical drills, and case study evaluations.
    """

    cohort = models.ForeignKey(
        "live_classes.Cohort",
        on_delete=models.CASCADE,
        related_name="activities",
        verbose_name=_("Cohort"),
    )
    course = models.ForeignKey(
        "lms.Course",
        on_delete=models.CASCADE,
        related_name="cohort_activities",
        verbose_name=_("Course"),
    )
    module = models.ForeignKey(
        "lms.Module",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cohort_activities",
        verbose_name=_("Module"),
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_cohort_activities",
        verbose_name=_("Tutor / Creator"),
    )
    title = models.CharField(_("Title (English)"), max_length=200)
    title_kinyarwanda = models.CharField(
        _("Title (Kinyarwanda)"), max_length=200, blank=True, default=""
    )
    description = models.TextField(_("Instructions (English)"))
    description_kinyarwanda = models.TextField(
        _("Instructions (Kinyarwanda)"), blank=True, default=""
    )

    activity_type = models.CharField(
        _("Activity Type"),
        max_length=30,
        choices=ActivityType.choices,
        default=ActivityType.ASSIGNMENT,
    )
    submission_type = models.CharField(
        _("Submission Type"),
        max_length=30,
        choices=ActivitySubmissionType.choices,
        default=ActivitySubmissionType.TEXT_RESPONSE,
    )

    total_points = models.PositiveIntegerField(_("Total Points"), default=100)
    passing_points = models.PositiveIntegerField(_("Passing Points"), default=70)

    due_date = models.DateTimeField(_("Due Date / Deadline"), null=True, blank=True)
    allow_late_submission = models.BooleanField(
        _("Allow Late Submissions"), default=False
    )

    is_published = models.BooleanField(
        _("Published to Cohort"), default=True, db_index=True
    )
    is_locked = models.BooleanField(_("Locked"), default=False, db_index=True)

    class Meta(BaseModel.Meta):
        verbose_name = _("Cohort Activity")
        verbose_name_plural = _("Cohort Activities")
        ordering = ["-due_date", "-created_at"]

    def __str__(self) -> str:
        return f"{self.title} ({self.cohort.name})"

    @property
    def submission_count(self) -> int:
        return self.submissions.count()

    @property
    def graded_count(self) -> int:
        return self.submissions.filter(
            status=StudentActivitySubmission.SubmissionStatus.GRADED
        ).count()


class StudentActivitySubmission(BaseModel):
    """
    Student response/submission to a tutor cohort activity, with scoring and feedback.
    """

    class SubmissionStatus(models.TextChoices):
        SUBMITTED = "SUBMITTED", _("Submitted")
        GRADED = "GRADED", _("Graded")
        RESUBMISSION_REQUESTED = "RESUBMISSION_REQUESTED", _("Resubmission Requested")

    activity = models.ForeignKey(
        CohortActivity,
        on_delete=models.CASCADE,
        related_name="submissions",
        verbose_name=_("Activity"),
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="activity_submissions",
        verbose_name=_("Student"),
    )
    submission_text = models.TextField(
        _("Written Submission"), blank=True, default=""
    )
    attachment = models.FileField(
        _("Uploaded File"),
        upload_to="lms/activities/submissions/",
        null=True,
        blank=True,
    )
    submitted_at = models.DateTimeField(_("Submitted At"), auto_now_add=True)
    status = models.CharField(
        _("Status"),
        max_length=30,
        choices=SubmissionStatus.choices,
        default=SubmissionStatus.SUBMITTED,
    )
    score = models.DecimalField(
        _("Score"), max_digits=5, decimal_places=2, null=True, blank=True
    )
    tutor_feedback = models.TextField(
        _("Tutor Feedback"), blank=True, default=""
    )
    graded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="graded_activity_submissions",
        verbose_name=_("Graded By"),
    )
    graded_at = models.DateTimeField(_("Graded At"), null=True, blank=True)

    class Meta(BaseModel.Meta):
        unique_together = ("activity", "student")
        verbose_name = _("Student Activity Submission")
        verbose_name_plural = _("Student Activity Submissions")
        ordering = ["-submitted_at"]

    def __str__(self) -> str:
        return f"{self.student.full_name or self.student.phone_number} → {self.activity.title} [{self.status}]"
