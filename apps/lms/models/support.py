from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class TicketRecipientRole(models.TextChoices):
    TUTOR = "TUTOR", _("Tutor / Instructor")
    TECH_SUPPORT = "TECH_SUPPORT", _("Technical Support Team")
    TRAINING_ADMIN = "TRAINING_ADMIN", _("Training Administrator / Operations")


class TicketCategory(models.TextChoices):
    CONTENT_INQUIRY = "CONTENT_INQUIRY", _("Course Content / Lesson Inquiry")
    TECHNICAL_ISSUE = "TECHNICAL_ISSUE", _("Technical / Platform Bug")
    EXAM_DISPUTE = "EXAM_DISPUTE", _("Mock Exam / Grade Question")
    ACCOUNT_BILLING = "ACCOUNT_BILLING", _("Account / Payment Issue")
    ADMINISTRATIVE = "ADMINISTRATIVE", _("Administrative / Operational Inquiry")
    OTHER = "OTHER", _("Other Inquiry")


class TicketPriority(models.TextChoices):
    LOW = "LOW", _("Low")
    MEDIUM = "MEDIUM", _("Medium")
    HIGH = "HIGH", _("High")
    URGENT = "URGENT", _("Urgent")


class TicketStatus(models.TextChoices):
    OPEN = "OPEN", _("Open")
    IN_PROGRESS = "IN_PROGRESS", _("In Progress")
    RESOLVED = "RESOLVED", _("Resolved")
    CLOSED = "CLOSED", _("Closed")
    REOPENED = "REOPENED", _("Reopened / Unsolved")


class TicketFeedbackRating(models.TextChoices):
    LIKE = "LIKE", _("Like")
    DISLIKE = "DISLIKE", _("Dislike")


class TicketFeedbackResolution(models.TextChoices):
    SOLVED = "SOLVED", _("Solved")
    UNSOLVED = "UNSOLVED", _("Unsolved")


class HelpTicket(BaseModel):
    """
    Support ticket created by a student, guest, or tutor requesting
    help from a tutor or the technical platform team. Collected and
    forwarded by Training Admin, with student resolution feedback.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="help_tickets",
        verbose_name=_("Requester"),
    )
    recipient_role = models.CharField(
        _("Addressed To"),
        max_length=20,
        choices=TicketRecipientRole.choices,
        default=TicketRecipientRole.TUTOR,
    )
    category = models.CharField(
        _("Category"),
        max_length=30,
        choices=TicketCategory.choices,
        default=TicketCategory.CONTENT_INQUIRY,
    )
    subject = models.CharField(
        _("Subject"),
        max_length=200,
    )
    message = models.TextField(
        _("Message / Details"),
    )
    priority = models.CharField(
        _("Priority"),
        max_length=20,
        choices=TicketPriority.choices,
        default=TicketPriority.MEDIUM,
    )
    status = models.CharField(
        _("Status"),
        max_length=20,
        choices=TicketStatus.choices,
        default=TicketStatus.OPEN,
        db_index=True,
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_tickets",
        verbose_name=_("Assigned Staff/Tutor"),
    )
    forwarded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tickets_forwarded_by",
        verbose_name=_("Forwarded By"),
    )
    forwarded_at = models.DateTimeField(
        _("Forwarded At"),
        null=True,
        blank=True,
    )
    internal_notes = models.TextField(
        _("Internal Notes / Admin Instructions"),
        blank=True,
        default="",
    )
    response = models.TextField(
        _("Resolution Response / Reply"),
        blank=True,
        default="",
    )
    resolved_at = models.DateTimeField(
        _("Resolved At"),
        null=True,
        blank=True,
    )

    # Student Feedback Fields
    feedback_rating = models.CharField(
        _("Student Feedback Rating"),
        max_length=20,
        choices=TicketFeedbackRating.choices,
        null=True,
        blank=True,
    )
    feedback_resolution = models.CharField(
        _("Student Feedback Resolution"),
        max_length=20,
        choices=TicketFeedbackResolution.choices,
        null=True,
        blank=True,
    )
    feedback_notes = models.TextField(
        _("Student Feedback Notes"),
        blank=True,
        default="",
    )
    feedback_submitted_at = models.DateTimeField(
        _("Feedback Submitted At"),
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = _("Help Ticket")
        verbose_name_plural = _("Help Tickets")
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.status}] {self.subject} ({self.user.phone_number})"

    def mark_resolved(self, response_text: str, resolver=None):
        self.status = TicketStatus.RESOLVED
        self.response = response_text
        if resolver:
            self.assigned_to = resolver
        self.resolved_at = timezone.now()
        self.save()

    def forward_to(self, assignee, forwarded_by=None, internal_notes=""):
        self.assigned_to = assignee
        self.forwarded_by = forwarded_by
        self.forwarded_at = timezone.now()
        if internal_notes:
            if self.internal_notes:
                self.internal_notes += f"\n---\n{internal_notes}"
            else:
                self.internal_notes = internal_notes
        if self.status == TicketStatus.OPEN:
            self.status = TicketStatus.IN_PROGRESS
        self.save()

    def update_status(self, new_status: str, response_text: str = "", updater=None, internal_notes: str = ""):
        self.status = new_status
        if response_text:
            self.response = response_text
        if updater and not self.assigned_to:
            self.assigned_to = updater
        if internal_notes:
            if self.internal_notes:
                self.internal_notes += f"\n---\n{internal_notes}"
            else:
                self.internal_notes = internal_notes
        if new_status in [TicketStatus.RESOLVED, TicketStatus.CLOSED] and not self.resolved_at:
            self.resolved_at = timezone.now()
        self.save()

    def submit_feedback(self, rating: str, resolution: str, notes: str = ""):
        self.feedback_rating = rating
        self.feedback_resolution = resolution
        self.feedback_notes = notes
        self.feedback_submitted_at = timezone.now()
        if resolution == TicketFeedbackResolution.UNSOLVED:
            self.status = TicketStatus.REOPENED
        self.save()
