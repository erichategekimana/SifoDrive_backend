"""
apps/audit/admin.py
====================
Read-only Django Admin for AuditLog.
No add/change/delete actions — enforced at model AND admin level.
"""

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import AuditLog, AuditSeverity


SEVERITY_COLORS = {
    AuditSeverity.LOW:      "#6b7280",  # gray
    AuditSeverity.MEDIUM:   "#d97706",  # amber
    AuditSeverity.HIGH:     "#dc2626",  # red
    AuditSeverity.CRITICAL: "#7c3aed",  # purple
}


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """
    Fully read-only audit log viewer.
    Provides severity-coloured display, full filtering, and hash verification status.
    """

    # ── Display ────────────────────────────────────────────────────────────────
    list_display = [
        "timestamp",
        "colored_severity",
        "action",
        "performed_by_phone",
        "ip_address",
        "object_type",
        "request_id_short",
        "hash_status",
    ]
    list_filter  = ["severity", "action", "http_method"]
    search_fields = [
        "performed_by_id",
        "target_user_id",
        "object_id",
        "request_id",
        "ip_address",
        "endpoint",
    ]
    date_hierarchy = "timestamp"
    ordering = ["-timestamp"]
    readonly_fields = [f.name for f in AuditLog._meta.get_fields()]  # ALL fields readonly

    # ── Pagination ─────────────────────────────────────────────────────────────
    list_per_page = 50

    # ── Disable all mutations ──────────────────────────────────────────────────
    def has_add_permission(self, request):    return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False

    # ── Custom display columns ─────────────────────────────────────────────────

    @admin.display(description=_("Severity"), ordering="severity")
    def colored_severity(self, obj):
        color = SEVERITY_COLORS.get(obj.severity, "#6b7280")
        return format_html(
            '<span style="color:{color}; font-weight:bold;">● {label}</span>',
            color=color,
            label=obj.get_severity_display(),
        )

    @admin.display(description=_("Request ID"))
    def request_id_short(self, obj):
        return obj.request_id[:8] + "…" if obj.request_id else "—"

    @admin.display(description=_("Hash ✓"))
    def hash_status(self, obj):
        if not obj.record_hash:
            return format_html('<span style="color:#d97706;">⚠ no hash</span>')
        if obj.verify_hash():
            return format_html('<span style="color:#16a34a;">✓ valid</span>')
        return format_html('<span style="color:#dc2626; font-weight:bold;">✗ TAMPERED</span>')

    # ── Detail view fieldsets ──────────────────────────────────────────────────
    fieldsets = (
        (_("Event"), {
            "fields": ("id", "timestamp", "action", "severity"),
        }),
        (_("Actor"), {
            "fields": ("performed_by_id", "performed_by_phone"),
        }),
        (_("Target"), {
            "fields": ("target_user_id", "object_type", "object_id"),
        }),
        (_("Request Context"), {
            "fields": ("ip_address", "user_agent", "request_id", "http_method", "endpoint"),
            "classes": ("collapse",),
        }),
        (_("Payload"), {
            "fields": ("context",),
        }),
        (_("Integrity"), {
            "fields": ("record_hash",),
            "classes": ("collapse",),
            "description": _(
                "SHA-256 hash of this record's canonical content. "
                "A mismatch with the computed hash indicates DB-level tampering."
            ),
        }),
    )
