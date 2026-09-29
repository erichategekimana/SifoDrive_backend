from django.db import models
from django.utils.translation import gettext_lazy as _


class ExamSessionStatus(models.TextChoices):
    PENDING = "PENDING", _("Pending Pre-flight")
    ACTIVE = "ACTIVE", _("In Progress")
    SUBMITTED = "SUBMITTED", _("Submitted — Awaiting Board Review")
    BOARD_REVIEW = "BOARD_REVIEW", _("Under Board Review")
    TRAINING_REVIEW = "TRAINING_REVIEW", _("Under Training Admin Review")
    SYSTEM_REVIEW = "SYSTEM_REVIEW", _("Awaiting System Admin Approval")
    APPROVED = "APPROVED", _("Approved — Certificate Auto-Generated")
    PUBLISHED = "PUBLISHED", _("Published — Official Results Released")
    FLAGGED = "FLAGGED", _("Flagged — Integrity Violation")
    REJECTED = "REJECTED", _("Rejected")
    EXPIRED = "EXPIRED", _("Expired — Time Limit Exceeded")


class CertificateTemplateType(models.TextChoices):
    STUDENT = "STUDENT", _("Student Enrolled (Cohort Theory Accreditation)")
    GUEST = "GUEST", _("Guest Diagnostic (Provisional Readiness Assessment)")
    ENTERPRISE = "ENTERPRISE", _("Enterprise Driving School (B2B Certified Lab)")
