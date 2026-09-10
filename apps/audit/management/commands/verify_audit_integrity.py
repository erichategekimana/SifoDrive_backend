"""
management/commands/verify_audit_integrity.py
===============================================
Django management command to verify the tamper-evident hash of every
AuditLog record in the database.

Usage:
  # Check all records (can be slow on large tables)
  python manage.py verify_audit_integrity

  # Check only the last N records
  python manage.py verify_audit_integrity --last 10000

  # Exit with non-zero code if any failures found (useful in CI/cron alerts)
  python manage.py verify_audit_integrity --fail-on-error

  # Write a JSON report file
  python manage.py verify_audit_integrity --report /var/log/sifo/audit_integrity.json

Suggested cron (daily at 02:00):
  0 2 * * * /path/to/venv/bin/python manage.py verify_audit_integrity --fail-on-error
"""

import json
import sys
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError

from apps.audit.models import AuditLog


class Command(BaseCommand):
    help = "Verify the SHA-256 hash of every AuditLog record to detect tampering."

    def add_arguments(self, parser):
        parser.add_argument(
            "--last",
            type=int,
            default=None,
            metavar="N",
            help="Only verify the most recent N records (default: all).",
        )
        parser.add_argument(
            "--fail-on-error",
            action="store_true",
            default=False,
            help="Exit with status code 1 if any hash mismatches are found.",
        )
        parser.add_argument(
            "--report",
            type=str,
            default=None,
            metavar="FILE",
            help="Write a JSON integrity report to this file path.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=500,
            help="Number of records to process per database query (default: 500).",
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n🔍  Sifo Drive — Audit Log Integrity Verification"
        ))
        self.stdout.write("━" * 60)

        qs = AuditLog.objects.order_by("-timestamp")
        if options["last"]:
            qs = qs[: options["last"]]
            self.stdout.write(f"   Scope: last {options['last']:,} records")
        else:
            self.stdout.write("   Scope: ALL records")

        total = qs.count()
        self.stdout.write(f"   Total records to check: {total:,}\n")

        if total == 0:
            self.stdout.write(self.style.WARNING("No audit log records found."))
            return

        # ── Batch processing ──────────────────────────────────────────────────
        checked = 0
        passed = 0
        failed = 0
        skipped = 0  # Records with no hash (pre-migration legacy records)
        tampered_ids = []
        batch_size = options["batch_size"]

        for offset in range(0, total, batch_size):
            batch = qs[offset : offset + batch_size]

            for log in batch:
                checked += 1

                if not log.record_hash:
                    skipped += 1
                    continue

                if log.verify_hash():
                    passed += 1
                else:
                    failed += 1
                    tampered_ids.append(str(log.id))
                    self.stdout.write(
                        self.style.ERROR(
                            f"   ✗ TAMPERED  id={log.id}  "
                            f"action={log.action}  "
                            f"timestamp={log.timestamp:%Y-%m-%d %H:%M:%S}"
                        )
                    )

            # Progress indicator every 10 batches
            if (offset // batch_size) % 10 == 0:
                pct = min(100, (checked / total) * 100)
                self.stdout.write(
                    f"   … {checked:,}/{total:,} ({pct:.0f}%)",
                    ending="\r",
                )

        # ── Results ───────────────────────────────────────────────────────────
        self.stdout.write("\n" + "━" * 60)
        self.stdout.write(f"   Total checked : {checked:,}")
        self.stdout.write(
            self.style.SUCCESS(f"   Passed        : {passed:,}") if passed else
            f"   Passed        : {passed:,}"
        )
        self.stdout.write(
            self.style.WARNING(f"   Skipped (no hash): {skipped:,}") if skipped else
            f"   Skipped (no hash): {skipped:,}"
        )

        if failed:
            self.stdout.write(
                self.style.ERROR(f"   ⚠  FAILED (TAMPERED): {failed:,}")
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f"   Failed        : {failed:,}  ✓ All hashes verified")
            )

        # ── JSON report ───────────────────────────────────────────────────────
        report_data = {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "scope": options["last"] or "all",
            "total_checked": checked,
            "passed": passed,
            "skipped_no_hash": skipped,
            "failed": failed,
            "all_passed": failed == 0,
            "tampered_ids": tampered_ids,
        }

        if options["report"]:
            try:
                with open(options["report"], "w") as f:
                    json.dump(report_data, f, indent=2)
                self.stdout.write(
                    self.style.SUCCESS(f"\n   Report written to: {options['report']}")
                )
            except OSError as exc:
                self.stderr.write(f"Could not write report: {exc}")

        self.stdout.write("")

        # ── Exit code ─────────────────────────────────────────────────────────
        if failed and options["fail_on_error"]:
            raise CommandError(
                f"{failed} audit log record(s) failed hash verification. "
                "This indicates potential database tampering. "
                "Investigate immediately and notify the DPO."
            )
