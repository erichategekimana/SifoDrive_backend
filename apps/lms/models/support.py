from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class TicketRecipientRole(models.TextChoices):
    TUTOR = "TUTOR", _("Tutor / Instructor")
    TECH_SUPPORT = "TECH_SUPPORT", _("Technical Support Team")


class TicketCategory(models.TextChoices):
    CONTENT_INQUIRY = "CONTENT_INQUIRY", _("Course Content / Lesson Inquiry")
    TECHNICAL_ISSUE = "TECHNICAL_ISSUE", _("Technical / Platform Bug")
    EXAM_DISPUTE = "EXAM_DISPUTE", _("Mock Exam / Grade Question")
    ACCOUNT_BILLING = "ACCOUNT_BILLING", _("Account / Payment Issue")
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


class HelpTicket(BaseModel):
    """
    Support ticket created by a student, guest, or tutor requesting
    help from a tutor or the technical platform team.
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
