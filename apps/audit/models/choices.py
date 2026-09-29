from django.db import models
from django.utils.translation import gettext_lazy as _


class AuditAction(models.TextChoices):
    """
    Complete catalogue of auditable events across all Sifo Drive apps.
    Every action maps to a specific severity level in AuditService.
    """

    # ── PII / National ID ───────────────────────────────────────────────────
    NID_ACCESS          = "NID_ACCESS",          _("National ID Accessed")
    NID_WRITE           = "NID_WRITE",           _("National ID Written")
    NID_PURGE           = "NID_PURGE",           _("National ID Purged")

    # ── User / Account ───────────────────────────────────────────────────────
    USER_REGISTERED     = "USER_REGISTERED",     _("User Registered")
    USER_VERIFIED       = "USER_VERIFIED",       _("Phone Number Verified")
    USER_SUSPENDED      = "USER_SUSPENDED",      _("User Suspended")
    USER_REACTIVATED    = "USER_REACTIVATED",    _("User Reactivated")
    ROLE_CHANGE         = "ROLE_CHANGE",         _("User Role Changed")
    GUEST_UPGRADED      = "GUEST_UPGRADED",      _("Guest Upgraded to Student")
    PASSWORD_RESET      = "PASSWORD_RESET",      _("Password Reset")
    ADMIN_LOGIN         = "ADMIN_LOGIN",         _("Admin Login")
    ADMIN_LOGOUT        = "ADMIN_LOGOUT",        _("Admin Logout")

    # ── Consent ─────────────────────────────────────────────────────────────
    CONSENT_TOS         = "CONSENT_TOS",         _("Terms of Service Accepted")
    CONSENT_PRIVACY     = "CONSENT_PRIVACY",     _("Privacy Policy Accepted")

    # ── Examinations ────────────────────────────────────────────────────────
    EXAM_STARTED        = "EXAM_STARTED",        _("Exam Session Started")
    EXAM_SUBMITTED      = "EXAM_SUBMITTED",      _("Exam Session Submitted")
    EXAM_FLAGGED        = "EXAM_FLAGGED",        _("Exam Session Flagged")
    EXAM_CERTIFIED      = "EXAM_CERTIFIED",      _("Exam Grade Certified")
    EXAM_REJECTED       = "EXAM_REJECTED",       _("Exam Grade Rejected")
    SNAPSHOT_CAPTURED   = "SNAPSHOT_CAPTURED",   _("Proctoring Snapshot Captured")
    SNAPSHOT_PURGE      = "SNAPSHOT_PURGE",      _("Proctoring Snapshots Purged")

    # ── Irembo Booking ───────────────────────────────────────────────────────
    BOOKING_CREATED     = "BOOKING_CREATED",     _("Booking Order Created")
    BOOKING_ACCESSED    = "BOOKING_ACCESSED",    _("Booking Record Accessed")
    BOOKING_STATE       = "BOOKING_STATE",       _("Booking State Changed")
    BOOKING_LOCKED      = "BOOKING_LOCKED",      _("Booking Locked by Agent")
    BOOKING_CONFIRMED   = "BOOKING_CONFIRMED",   _("Booking Slot Confirmed")
    BOOKING_EXHAUSTED   = "BOOKING_EXHAUSTED",   _("Booking Slots Exhausted")
    BOOKING_REFUNDED    = "BOOKING_REFUNDED",    _("Booking Refunded")

    # ── Payments ─────────────────────────────────────────────────────────────
    PAYMENT_INITIATED   = "PAYMENT_INITIATED",   _("Payment Initiated")
    PAYMENT_SUCCESS     = "PAYMENT_SUCCESS",     _("Payment Succeeded")
    PAYMENT_FAILED      = "PAYMENT_FAILED",      _("Payment Failed")
    PAYMENT_REFUNDED    = "PAYMENT_REFUNDED",    _("Payment Refunded")

    # ── LMS / Content ────────────────────────────────────────────────────────
    CONTENT_PUBLISHED   = "CONTENT_PUBLISHED",   _("Course Content Published")
    CONTENT_DELETED     = "CONTENT_DELETED",     _("Course Content Deleted")
    QUESTION_CREATED    = "QUESTION_CREATED",    _("Question Bank Entry Created")

    # ── Compliance / System ──────────────────────────────────────────────────
    PII_EXPORT          = "PII_EXPORT",          _("PII Data Exported")
    DATA_RETENTION_RUN  = "DATA_RETENTION_RUN",  _("Data Retention Policy Executed")
    INTEGRITY_CHECK     = "INTEGRITY_CHECK",     _("Audit Log Integrity Checked")
    SYSTEM_CONFIG       = "SYSTEM_CONFIG",       _("System Configuration Changed")


class AuditSeverity(models.TextChoices):
    LOW      = "LOW",      _("Low")
    MEDIUM   = "MEDIUM",   _("Medium")
    HIGH     = "HIGH",     _("High")
    CRITICAL = "CRITICAL", _("Critical")


# Severity mapping — defined here so AuditService can reference it
SEVERITY_MAP: dict[str, str] = {
    # Critical — PII direct access / data destruction / consent override
    AuditAction.NID_ACCESS:         AuditSeverity.CRITICAL,
    AuditAction.NID_WRITE:          AuditSeverity.CRITICAL,
    AuditAction.NID_PURGE:          AuditSeverity.CRITICAL,
    AuditAction.PII_EXPORT:         AuditSeverity.CRITICAL,
    AuditAction.USER_SUSPENDED:     AuditSeverity.CRITICAL,
    AuditAction.EXAM_FLAGGED:       AuditSeverity.CRITICAL,
    AuditAction.SNAPSHOT_PURGE:     AuditSeverity.CRITICAL,
    AuditAction.DATA_RETENTION_RUN: AuditSeverity.CRITICAL,
    AuditAction.SYSTEM_CONFIG:      AuditSeverity.CRITICAL,

    # High — role/account lifecycle, payments, booking state changes
    AuditAction.ROLE_CHANGE:        AuditSeverity.HIGH,
    AuditAction.GUEST_UPGRADED:     AuditSeverity.HIGH,
    AuditAction.ADMIN_LOGIN:        AuditSeverity.HIGH,
    AuditAction.BOOKING_ACCESSED:   AuditSeverity.HIGH,
    AuditAction.BOOKING_STATE:      AuditSeverity.HIGH,
    AuditAction.BOOKING_LOCKED:     AuditSeverity.HIGH,
    AuditAction.BOOKING_CONFIRMED:  AuditSeverity.HIGH,
    AuditAction.BOOKING_REFUNDED:   AuditSeverity.HIGH,
    AuditAction.PAYMENT_REFUNDED:   AuditSeverity.HIGH,
    AuditAction.EXAM_CERTIFIED:     AuditSeverity.HIGH,
    AuditAction.EXAM_REJECTED:      AuditSeverity.HIGH,

    # Medium — exam flow, payments, consent, content management
    AuditAction.EXAM_STARTED:       AuditSeverity.MEDIUM,
    AuditAction.EXAM_SUBMITTED:     AuditSeverity.MEDIUM,
    AuditAction.SNAPSHOT_CAPTURED:  AuditSeverity.MEDIUM,
    AuditAction.BOOKING_CREATED:    AuditSeverity.MEDIUM,
    AuditAction.PAYMENT_INITIATED:  AuditSeverity.MEDIUM,
    AuditAction.PAYMENT_SUCCESS:    AuditSeverity.MEDIUM,
    AuditAction.PAYMENT_FAILED:     AuditSeverity.MEDIUM,
    AuditAction.CONSENT_PRIVACY:    AuditSeverity.MEDIUM,
    AuditAction.USER_REACTIVATED:   AuditSeverity.MEDIUM,
    AuditAction.PASSWORD_RESET:     AuditSeverity.MEDIUM,
    AuditAction.CONTENT_DELETED:    AuditSeverity.MEDIUM,

    # Low — routine informational events
    AuditAction.USER_REGISTERED:    AuditSeverity.LOW,
    AuditAction.USER_VERIFIED:      AuditSeverity.LOW,
    AuditAction.ADMIN_LOGOUT:       AuditSeverity.LOW,
    AuditAction.CONSENT_TOS:        AuditSeverity.LOW,
    AuditAction.CONTENT_PUBLISHED:  AuditSeverity.LOW,
    AuditAction.QUESTION_CREATED:   AuditSeverity.LOW,
    AuditAction.INTEGRITY_CHECK:    AuditSeverity.LOW,
    AuditAction.BOOKING_EXHAUSTED:  AuditSeverity.MEDIUM,
}
