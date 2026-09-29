import hashlib
import json
import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _

from .choices import AuditAction, AuditSeverity, SEVERITY_MAP


def _extract_ip(request) -> str | None:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR") or None


def _last4(phone: str) -> str:
    """Return only the last 4 digits of a phone number (privacy preservation)."""
    return phone[-4:] if phone and len(phone) >= 4 else phone


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


class AuditLogManager(models.Manager.from_queryset(AuditLogQuerySet)):
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
        app_label = "audit"
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
