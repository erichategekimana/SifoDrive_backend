"""
apps/accounts/constants.py
===========================
Enumerations and constants for the accounts domain.
Centralizing these prevents magic strings scattered across the codebase.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _


class UserRole(models.TextChoices):
    """
    Six-tier user role system as defined in the Sifo Drive specification.
    Each role maps to a distinct permission set enforced in apps/core/permissions.py.
    """

    STUDENT = "STUDENT", _("Student")
    """
    Formally enrolled learner. Has a unique Student ID (SIFO-STU-YYYY-XXXX),
    pays tuition via MoMo, attends live Google Meet classes, and must satisfy
    eligibility criteria before accessing the exam engine.
    """

    GUEST = "GUEST", _("Guest")
    """
    Free-tier self-registered account. Access is limited to introductory
    content. Can pay a per-exam fee via MoMo for mock exam access.
    No live tutoring, no Google Meet links.
    """

    TUTOR = "TUTOR", _("Tutor / Facilitator")
    """
    Course author and live-class facilitator. Can create/edit curriculum modules,
    manage question banks, schedule Google Meet sessions, and supervise student
    progress metrics.
    """

    ENTERPRISE_ADMIN = "ENTERPRISE_ADMIN", _("Enterprise Admin")
    """
    Driving school director. Manages multi-station B2B lab account with
    concurrent exam sessions up to the school's license quota.
    No individual student proctoring — physical supervision by instructor.
    """

    BOARD_REVIEWER = "BOARD_REVIEWER", _("Board Reviewer")
    """
    Internal examiner who reviews flagged B2C exam sessions (proctoring
    snapshots, violation logs) and certifies or rejects student grades
    before they become official.
    """

    TRAINING_ADMIN = "TRAINING_ADMIN", _("Training Administrator")
    """
    Pedagogical administrator. Manages courses, modules, lessons, learning
    materials, and quiz banks. Can create, edit, update, publish, and delete curriculum.
    """

    AGENT = "AGENT", _("Agent / Sifo Drive Agent")
    """
    Field / kiosk agent. Can create client accounts, facilitate bookings,
    subscription purchases, and service payments. Earns configured commissions
    per service paid out monthly (30-day cycle).
    """

    SYSTEM_ADMIN = "SYSTEM_ADMIN", _("System Admin")
    """
    Full platform control. Manages users, content, timetables, payments,
    Irembo queue, and compliance configurations. Generates PII audit reports.
    """


class CommissionServiceType(models.TextChoices):
    """Platform services for which agents can earn commission fees."""
    BOOKING = "BOOKING", _("Driving Test Booking Concierge")
    SUBSCRIPTION = "SUBSCRIPTION", _("Course Subscription")
    EXAM_PURCHASE = "EXAM_PURCHASE", _("Single / Multi Exam Purchase")
    LEARNING_FEE = "LEARNING_FEE", _("Tuition / Learning Fee")
    OTHER = "OTHER", _("Other Facilitated Service")


class CommissionStatus(models.TextChoices):
    """Commission ledger settlement states."""
    ACCRUED = "ACCRUED", _("Accrued (Pending Monthly Payout)")
    PAID_OUT = "PAID_OUT", _("Paid Out")
    CANCELLED = "CANCELLED", _("Cancelled")


class AccountStatus(models.TextChoices):
    """User account lifecycle states."""
    ACTIVE = "ACTIVE", _("Active")
    PENDING_VERIFICATION = "PENDING_VERIFICATION", _("Pending Phone Verification")
    SUSPENDED = "SUSPENDED", _("Suspended")
    DEACTIVATED = "DEACTIVATED", _("Deactivated")
    BLACKLISTED = "BLACKLISTED", _("Blacklisted")


class LicenseCategory(models.TextChoices):
    """Rwandan driving license categories used in Irembo booking."""
    A = "A", _("Category A — Motorcycles")
    B = "B", _("Category B — Light Motor Vehicles")
    C = "C", _("Category C — Heavy Motor Vehicles")
    D = "D", _("Category D — Passenger Buses")
    E = "E", _("Category E — Articulated Vehicles")
    F = "F", _("Category F — Agricultural Vehicles")
