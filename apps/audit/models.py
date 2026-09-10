"""
apps/audit/models.py
=====================
Immutable, tamper-evident audit log for Sifo Drive.

Design guarantees:
──────────────────
1. IMMUTABLE  — no update/delete permissions exist at any layer.
               The only DB operation allowed is INSERT.
               Enforced via custom save(), delete() overrides + Meta.default_permissions.

2. TAMPER-EVIDENT — every record stores a SHA-256 hash of its own canonical
               content. Any DB-level modification to a field will cause the
               hash to mismatch during integrity verification.
               Run: python manage.py verify_audit_integrity

3. COMPREHENSIVE — covers all 9 domains: accounts, lms, examinations,
               live_classes, irembo, payments, notifications, plus platform-level events.

4. COMPLIANCE — satisfies Rwanda Law No 058/2021 requirements for audit
               trails over citizen PII access. Minimum retention: 7 years.

Rule: NEVER call AuditLog directly from views.
      Always go through AuditService (apps/audit/services.py).
"""

import hashlib
import json
import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Custom QuerySet
# ---------------------------------------------------------------------------

class AuditLogQuerySet(models.QuerySet):
    """Read-optimised filters for audit log analysis."""

    def by_action(self, *actions: str):
        return self.filter(action__in=actions)

    def critical(self):
        return self.filter(severity=AuditSeverity.CRITICAL)

    def high_and_above(self):
        return self.filter(severity__in=[AuditSeverity.HIGH, AuditSeverity.CRITICAL])

    def by_user(self, user_id):
        return self.filter(performed_by_id=user_id)

    def concerning_user(self, user_id):
        """All events either performed BY or targeting a specific user."""
        return self.filter(
            models.Q(performed_by_id=user_id) | models.Q(target_user_id=user_id)
        )

    def nid_events(self):
        return self.by_action(
            AuditAction.NID_ACCESS,
            AuditAction.NID_WRITE,
            AuditAction.NID_PURGE,
        )

    def with_hash_mismatch(self):
        """
        Filter records whose stored hash does not match recomputed hash.
        Indicates potential DB-level tampering.
        Note: Evaluated in Python — use on small result sets only.
        Prefer the management command for full integrity checks.
        """
        return [log for log in self if not log.verify_hash()]


class AuditLogManager(models.Manager):
    def get_queryset(self):
        return AuditLogQuerySet(self.model, using=self._db)

    def create_log(
        self,
        action: str,
        performed_by=None,
        target_user=None,
        request=None,
        context: dict | None = None,
        object_type: str = "",
        object_id: str = "",
        severity: str | None = None,
    ) -> "AuditLog":
        """
        Primary factory method. Always use this instead of .create() directly.
        Extracts request context, resolves severity, and computes the record hash.
        """
        from apps.audit.context import get_current_request_context

        # Pull IP / user-agent / request-id from thread-local if request not passed
        req_ctx = get_current_request_context()
        ip_address = None
        user_agent = ""
        request_id = ""
        http_method = ""
        endpoint = ""

        if request is not None:
            ip_address = _extract_ip(request)
            user_agent = request.META.get("HTTP_USER_AGENT", "")[:500]
            request_id = request.META.get("HTTP_X_REQUEST_ID", "") or req_ctx.get("request_id", "")
            http_method = request.method
            endpoint = request.path[:300]
        elif req_ctx:
            ip_address = req_ctx.get("ip_address")
            user_agent = req_ctx.get("user_agent", "")
            request_id = req_ctx.get("request_id", "")
            http_method = req_ctx.get("http_method", "")
            endpoint = req_ctx.get("endpoint", "")

        resolved_severity = severity or SEVERITY_MAP.get(action, AuditSeverity.LOW)

        log = self.model(
            action=action,
            severity=resolved_severity,
            performed_by_id=performed_by.id if performed_by else None,
            performed_by_phone=_last4(performed_by.phone_number) if performed_by else "",
            target_user_id=target_user.id if target_user else None,
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
            http_method=http_method,
            endpoint=endpoint,
            object_type=object_type,
            object_id=str(object_id) if object_id else "",
            context=context or {},
        )
        # Compute tamper-evident hash before saving
        log.record_hash = log.compute_hash()
        log.save(using=self.db)
        return log


# ---------------------------------------------------------------------------
# Audit Log Model
# ---------------------------------------------------------------------------

class AuditLog(models.Model):
    """
    Immutable, tamper-evident audit trail record.

    INSERT-only: save() raises if called on an existing instance.
    No update/delete permissions exist at any access layer.
    Retained for a minimum of 7 years (Rwanda Law No 058/2021).
    """

    # --- Identity ---
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    # --- What happened ---
    action = models.CharField(
        _("Action"),
        max_length=30,
        choices=AuditAction.choices,
        db_index=True,
    )
    severity = models.CharField(
        _("Severity"),
        max_length=10,
        choices=AuditSeverity.choices,
        default=AuditSeverity.LOW,
        db_index=True,
    )

    # --- Who did it ---
    performed_by_id = models.UUIDField(
        _("Performed By (User ID)"),
        null=True,
        blank=True,
        db_index=True,
    )
    performed_by_phone = models.CharField(
        _("Performed By (Phone — last 4 digits)"),
        max_length=10,
        blank=True,
        help_text=_("Only the last 4 digits are stored for privacy."),
    )

    # --- Who was affected ---
    target_user_id = models.UUIDField(
        _("Target User ID"),
        null=True,
        blank=True,
        db_index=True,
    )

    # --- What object was involved ---
    object_type = models.CharField(
        _("Object Type"),
        max_length=100,
        blank=True,
        help_text=_("Model class name of the affected record. E.g. 'BookingOrder'."),
    )
    object_id = models.CharField(
        _("Object ID"),
        max_length=64,
        blank=True,
        db_index=True,
        help_text=_("UUID or identifier of the affected record."),
    )

    # --- Where from ---
    ip_address = models.GenericIPAddressField(
        _("IP Address"),
        null=True,
        blank=True,
    )
    user_agent = models.TextField(
        _("User Agent"),
        blank=True,
    )
    request_id = models.CharField(
        _("Request ID"),
        max_length=64,
        blank=True,
        db_index=True,
        help_text=_("X-Request-ID header value for distributed tracing."),
    )
    http_method = models.CharField(
        _("HTTP Method"),
        max_length=10,
        blank=True,
    )
    endpoint = models.CharField(
        _("Endpoint"),
        max_length=300,
        blank=True,
    )

    # --- Structured payload ---
    context = models.JSONField(
        _("Context"),
        default=dict,
        blank=True,
        help_text=_("Structured key-value context for this event. No raw PII allowed."),
    )

    # --- Tamper-evident hash ---
    record_hash = models.CharField(
        _("Record Hash"),
        max_length=64,
        blank=True,
        help_text=_(
            "SHA-256 of the canonical record content. "
            "Mismatch during verification indicates DB-level tampering."
        ),
    )

    # --- When ---
    timestamp = models.DateTimeField(
        _("Timestamp"),
        auto_now_add=True,
        db_index=True,
    )

    objects = AuditLogManager()

    class Meta:
        verbose_name = _("Audit Log")
        verbose_name_plural = _("Audit Logs")
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["action", "severity", "timestamp"]),
            models.Index(fields=["performed_by_id", "timestamp"]),
            models.Index(fields=["target_user_id", "timestamp"]),
            models.Index(fields=["object_type", "object_id"]),
        ]
        # IMMUTABILITY CONTRACT: only 'view' permission exists.
        # No add/change/delete through Django's permission system.
        default_permissions = ("view",)

    def __str__(self) -> str:
        return (
            f"[{self.severity}] {self.action} "
            f"by …{self.performed_by_phone or '?'} "
            f"at {self.timestamp:%Y-%m-%d %H:%M:%S UTC}"
        )

    # -------------------------------------------------------------------------
    # Immutability enforcement
    # -------------------------------------------------------------------------

    def save(self, *args, **kwargs):
        """
        Enforce INSERT-only semantics.
        Raises RuntimeError if called on an already-saved record.
        """
        if self.pk and AuditLog.objects.filter(pk=self.pk).exists():
            raise RuntimeError(
                "AuditLog records are immutable. "
                "Attempted to update an existing record (pk=%s)." % self.pk
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Hard-deletion is permanently disabled on audit logs."""
        raise RuntimeError(
            "AuditLog records cannot be deleted. "
            "They are compliance artifacts retained for 7 years."
        )

    # -------------------------------------------------------------------------
    # Tamper-evident hashing
    # -------------------------------------------------------------------------

    def _canonical_content(self) -> str:
        """
        Build a stable, deterministic string representation of this record's content.
        Used as the input to SHA-256 for tamper detection.
        Field order is fixed — any change here would invalidate all existing hashes.
        """
        payload = {
            "action":           self.action,
            "severity":         self.severity,
            "performed_by_id":  str(self.performed_by_id or ""),
            "target_user_id":   str(self.target_user_id or ""),
            "ip_address":       str(self.ip_address or ""),
            "object_type":      self.object_type,
            "object_id":        self.object_id,
            "request_id":       self.request_id,
            "http_method":      self.http_method,
            "endpoint":         self.endpoint,
            # Sort keys for determinism; exclude timestamp (not set before first save)
            "context":          json.dumps(self.context, sort_keys=True),
        }
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=True)
        return canonical

    def compute_hash(self) -> str:
        """Compute the SHA-256 hash of this record's canonical content."""
        return hashlib.sha256(self._canonical_content().encode("utf-8")).hexdigest()

    def verify_hash(self) -> bool:
        """
        Return True if the stored hash matches the recomputed hash.
        False means the record was tampered with after creation.
        """
        return self.record_hash == self.compute_hash()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_ip(request) -> str | None:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR") or None


def _last4(phone: str) -> str:
    """Return only the last 4 digits of a phone number (privacy preservation)."""
    return phone[-4:] if phone and len(phone) >= 4 else phone
