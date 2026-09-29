import logging

from apps.audit.models import AuditAction, AuditLog

logger = logging.getLogger("apps.audit.services.audit_service")


def _safe_log(**kwargs) -> AuditLog | None:
    """
    Wrapper around AuditLog.objects.create_log() that swallows exceptions.
    Any error is logged to the audit service logger for ops alerting
    but the exception is never propagated to the caller.
    """
    try:
        return AuditLog.objects.create_log(**kwargs)
    except Exception as exc:
        logger.critical(
            "AUDIT LOG WRITE FAILURE | action=%s error=%s",
            kwargs.get("action", "?"),
            exc,
            exc_info=True,
        )
        return None


class AuditService:
    """
    Typed factory methods for every auditable event in Sifo Drive.
    Group by domain for readability and discoverability.
    """

    # =========================================================================
    # USER / ACCOUNT EVENTS
    # =========================================================================

    @classmethod
    def log_user_registered(cls, user, request=None) -> None:
        """Fired when any new account (guest or student) is created."""
        _safe_log(
            action=AuditAction.USER_REGISTERED,
            performed_by=user,
            target_user=user,
            request=request,
            context={
                "role": user.role,
                "phone_suffix": user.phone_number[-4:],
            },
        )

    @classmethod
    def log_user_verified(cls, user, request=None) -> None:
        """Fired when a user's phone is confirmed via OTP."""
        _safe_log(
            action=AuditAction.USER_VERIFIED,
            performed_by=user,
            target_user=user,
            request=request,
            context={"role": user.role},
        )

    @classmethod
    def log_user_suspended(cls, target_user, performed_by, reason: str = "", request=None) -> None:
        """Fired when SYSTEM_ADMIN suspends a user account."""
        _safe_log(
            action=AuditAction.USER_SUSPENDED,
            performed_by=performed_by,
            target_user=target_user,
            request=request,
            context={
                "reason": reason[:500],
                "target_role": target_user.role,
                "target_status": target_user.status,
            },
        )

    @classmethod
    def log_user_reactivated(cls, target_user, performed_by, request=None) -> None:
        _safe_log(
            action=AuditAction.USER_REACTIVATED,
            performed_by=performed_by,
            target_user=target_user,
            request=request,
        )

    @classmethod
    def log_role_change(
        cls,
        target_user,
        old_role: str,
        new_role: str,
        performed_by,
        request=None,
    ) -> None:
        """Fired whenever a user's role is changed by an admin."""
        _safe_log(
            action=AuditAction.ROLE_CHANGE,
            performed_by=performed_by,
            target_user=target_user,
            request=request,
            context={
                "old_role": old_role,
                "new_role": new_role,
            },
        )

    @classmethod
    def log_guest_upgraded(cls, user, request=None) -> None:
        """Fired when a GUEST account is promoted to STUDENT."""
        _safe_log(
            action=AuditAction.GUEST_UPGRADED,
            performed_by=user,
            target_user=user,
            request=request,
            context={"new_role": "STUDENT"},
        )

    @classmethod
    def log_password_reset(cls, user, request=None) -> None:
        _safe_log(
            action=AuditAction.PASSWORD_RESET,
            performed_by=user,
            target_user=user,
            request=request,
        )

    @classmethod
    def log_admin_login(cls, user, request=None) -> None:
        _safe_log(
            action=AuditAction.ADMIN_LOGIN,
            performed_by=user,
            request=request,
            context={"role": user.role},
        )

    @classmethod
    def log_admin_logout(cls, user, request=None) -> None:
        _safe_log(
            action=AuditAction.ADMIN_LOGOUT,
            performed_by=user,
            request=request,
        )

    # =========================================================================
    # CONSENT EVENTS
    # =========================================================================

    @classmethod
    def log_consent_tos(cls, user, request=None) -> None:
        """Fired when a user explicitly accepts the Terms of Service."""
        _safe_log(
            action=AuditAction.CONSENT_TOS,
            performed_by=user,
            target_user=user,
            request=request,
            context={"role": user.role},
        )

    @classmethod
    def log_consent_privacy(cls, user, request=None) -> None:
        """
        Fired when a user accepts the Privacy Policy.
        Critical for Rwanda Law No 058/2021 Articles 6 & 17 compliance.
        """
        _safe_log(
            action=AuditAction.CONSENT_PRIVACY,
            performed_by=user,
            target_user=user,
            request=request,
            context={
                "role": user.role,
                "triggered_by": "user_action",
            },
        )

    # =========================================================================
    # PII / NATIONAL ID EVENTS  (highest sensitivity — CRITICAL severity)
    # =========================================================================

    @classmethod
    def log_nid_access(cls, accessing_user, target_user, reason: str = "", request=None) -> None:
        """
        Fired every time any agent or admin reads a decrypted National ID number.
        This is the most critical audit event — required by Art. 40, Law 058/2021.

        context.reason should explain WHY the NID was accessed.
        """
        _safe_log(
            action=AuditAction.NID_ACCESS,
            performed_by=accessing_user,
            target_user=target_user,
            request=request,
            object_type="User",
            object_id=str(target_user.id),
            context={
                "reason": reason[:500],
                "accessor_role": accessing_user.role,
            },
        )

    @classmethod
    def log_nid_write(cls, writing_user, target_user, request=None) -> None:
        """Fired when a National ID is stored or updated (encrypted)."""
        _safe_log(
            action=AuditAction.NID_WRITE,
            performed_by=writing_user,
            target_user=target_user,
            request=request,
            object_type="User",
            object_id=str(target_user.id),
            context={"writer_role": writing_user.role},
        )

    @classmethod
    def log_nid_purge(cls, purged_by, target_user, request=None) -> None:
        """Fired when National ID data is purged as part of data retention."""
        _safe_log(
            action=AuditAction.NID_PURGE,
            performed_by=purged_by,
            target_user=target_user,
            request=request,
            object_type="User",
            object_id=str(target_user.id),
        )

    @classmethod
    def log_pii_export(cls, performed_by, record_count: int, export_type: str, request=None) -> None:
        """Fired when any bulk PII export is generated."""
        _safe_log(
            action=AuditAction.PII_EXPORT,
            performed_by=performed_by,
            request=request,
            context={
                "export_type": export_type,
                "record_count": record_count,
            },
        )

    # =========================================================================
    # EXAMINATION EVENTS
    # =========================================================================

    @classmethod
    def log_exam_started(cls, session, user, request=None) -> None:
        _safe_log(
            action=AuditAction.EXAM_STARTED,
            performed_by=user,
            target_user=user,
            request=request,
            object_type="ExamSession",
            object_id=str(session.id),
            context={
                "track": session.track,
                "device_fingerprint": session.device_fingerprint[:20] if session.device_fingerprint else "",
            },
        )

    @classmethod
    def log_exam_submitted(cls, session, user, score: int, passed: bool, request=None) -> None:
        _safe_log(
            action=AuditAction.EXAM_SUBMITTED,
            performed_by=user,
            target_user=user,
            request=request,
            object_type="ExamSession",
            object_id=str(session.id),
            context={
                "score": score,
                "passed": passed,
                "track": session.track,
                "violation_count": session.violation_count,
            },
        )

    @classmethod
    def log_exam_flagged(
        cls,
        session,
        flagging_user,
        violation_type: str,
        violation_count: int,
        request=None,
    ) -> None:
        """
        Fired when an exam is auto-flagged by the proctoring engine
        or manually flagged by a board reviewer.
        """
        _safe_log(
            action=AuditAction.EXAM_FLAGGED,
            performed_by=flagging_user,
            target_user=session.student,
            request=request,
            object_type="ExamSession",
            object_id=str(session.id),
            context={
                "violation_type": violation_type,
                "violation_count": violation_count,
                "auto_flagged": flagging_user.id == session.student.id,
            },
        )

    @classmethod
    def log_exam_certified(cls, session, reviewer, request=None) -> None:
        """Fired when a Board Reviewer certifies an exam result."""
        _safe_log(
            action=AuditAction.EXAM_CERTIFIED,
            performed_by=reviewer,
            target_user=session.student,
            request=request,
            object_type="ExamSession",
            object_id=str(session.id),
            context={
                "score": session.score,
                "passed": session.passed,
            },
        )

    @classmethod
    def log_exam_rejected(cls, session, reviewer, reason: str, request=None) -> None:
        """Fired when a Board Reviewer rejects an exam result (integrity violation)."""
        _safe_log(
            action=AuditAction.EXAM_REJECTED,
            performed_by=reviewer,
            target_user=session.student,
            request=request,
            object_type="ExamSession",
            object_id=str(session.id),
            context={"reason": reason[:500]},
        )

    @classmethod
    def log_snapshot_captured(cls, session, event_type: str, request=None) -> None:
        """Fired for every webcam snapshot (scheduled or anomaly-triggered)."""
        _safe_log(
            action=AuditAction.SNAPSHOT_CAPTURED,
            performed_by=session.student,
            request=request,
            object_type="ExamSession",
            object_id=str(session.id),
            context={"event_type": event_type},
        )

    @classmethod
    def log_snapshot_purge(cls, performed_by, purged_count: int, request=None) -> None:
        """
        Fired when the scheduled data retention task deletes proctoring snapshots
        older than 30 days (COMPLIANCE.PROCTORING_SNAPSHOT_RETENTION_DAYS).
        """
        _safe_log(
            action=AuditAction.SNAPSHOT_PURGE,
            performed_by=performed_by,
            request=request,
            context={
                "purged_count": purged_count,
                "retention_policy_days": 30,
            },
        )

    # =========================================================================
    # IREMBO BOOKING EVENTS
    # =========================================================================

    @classmethod
    def log_booking_created(cls, booking, user, request=None) -> None:
        _safe_log(
            action=AuditAction.BOOKING_CREATED,
            performed_by=user,
            target_user=user,
            request=request,
            object_type="BookingOrder",
            object_id=str(booking.id),
            context={
                "ticket_number": booking.ticket_number,
                "license_category": booking.license_category,
            },
        )

    @classmethod
    def log_booking_accessed(cls, booking, accessing_user, request=None) -> None:
        """Fired every time an agent opens a booking record (reads NID/applicant details)."""
        _safe_log(
            action=AuditAction.BOOKING_ACCESSED,
            performed_by=accessing_user,
            target_user=booking.applicant,
            request=request,
            object_type="BookingOrder",
            object_id=str(booking.id),
            context={
                "ticket_number": booking.ticket_number,
                "booking_state": booking.state,
            },
        )

    @classmethod
    def log_booking_state_changed(
        cls,
        booking,
        old_state: str,
        new_state: str,
        performed_by,
        request=None,
    ) -> None:
        _safe_log(
            action=AuditAction.BOOKING_STATE,
            performed_by=performed_by,
            target_user=booking.applicant,
            request=request,
            object_type="BookingOrder",
            object_id=str(booking.id),
            context={
                "ticket_number": booking.ticket_number,
                "old_state": old_state,
                "new_state": new_state,
            },
        )

    @classmethod
    def log_booking_locked(cls, booking, agent, request=None) -> None:
        _safe_log(
            action=AuditAction.BOOKING_LOCKED,
            performed_by=agent,
            target_user=booking.applicant,
            request=request,
            object_type="BookingOrder",
            object_id=str(booking.id),
            context={"ticket_number": booking.ticket_number},
        )

    @classmethod
    def log_booking_confirmed(cls, booking, agent, application_number: str, request=None) -> None:
        _safe_log(
            action=AuditAction.BOOKING_CONFIRMED,
            performed_by=agent,
            target_user=booking.applicant,
            request=request,
            object_type="BookingOrder",
            object_id=str(booking.id),
            context={
                "ticket_number": booking.ticket_number,
                "irembo_application_number": application_number,
                "test_date": str(booking.confirmed_test_date or ""),
            },
        )

    @classmethod
    def log_booking_refunded(cls, booking, performed_by, reason: str = "", request=None) -> None:
        _safe_log(
            action=AuditAction.BOOKING_REFUNDED,
            performed_by=performed_by,
            target_user=booking.applicant,
            request=request,
            object_type="BookingOrder",
            object_id=str(booking.id),
            context={
                "ticket_number": booking.ticket_number,
                "reason": reason[:500],
            },
        )

    # =========================================================================
    # PAYMENT EVENTS
    # =========================================================================

    @classmethod
    def log_payment_initiated(cls, transaction, user, request=None) -> None:
        _safe_log(
            action=AuditAction.PAYMENT_INITIATED,
            performed_by=user,
            target_user=user,
            request=request,
            object_type="Transaction",
            object_id=str(transaction.id),
            context={
                "provider": transaction.provider,
                "fee_type": transaction.fee_type,
                "amount": str(transaction.amount),
            },
        )

    @classmethod
    def log_payment_success(cls, transaction, request=None) -> None:
        _safe_log(
            action=AuditAction.PAYMENT_SUCCESS,
            performed_by=transaction.payer,
            target_user=transaction.payer,
            request=request,
            object_type="Transaction",
            object_id=str(transaction.id),
            context={
                "provider": transaction.provider,
                "fee_type": transaction.fee_type,
                "amount": str(transaction.amount),
                "provider_tx_id": transaction.provider_transaction_id or "",
            },
        )

    @classmethod
    def log_payment_failed(cls, transaction, reason: str, request=None) -> None:
        _safe_log(
            action=AuditAction.PAYMENT_FAILED,
            performed_by=transaction.payer,
            target_user=transaction.payer,
            request=request,
            object_type="Transaction",
            object_id=str(transaction.id),
            context={
                "provider": transaction.provider,
                "fee_type": transaction.fee_type,
                "reason": reason[:500],
            },
        )

    # =========================================================================
    # DATA RETENTION / COMPLIANCE EVENTS
    # =========================================================================

    @classmethod
    def log_data_retention_run(
        cls,
        performed_by,
        purge_type: str,
        record_count: int,
        request=None,
    ) -> None:
        """Fired whenever an automated data retention job runs."""
        _safe_log(
            action=AuditAction.DATA_RETENTION_RUN,
            performed_by=performed_by,
            request=request,
            context={
                "purge_type": purge_type,
                "record_count": record_count,
            },
        )

    @classmethod
    def log_integrity_check(
        cls,
        performed_by,
        total_checked: int,
        failed_count: int,
        request=None,
    ) -> None:
        """Fired after running python manage.py verify_audit_integrity."""
        _safe_log(
            action=AuditAction.INTEGRITY_CHECK,
            performed_by=performed_by,
            request=request,
            context={
                "total_checked": total_checked,
                "failed_count": failed_count,
                "all_passed": failed_count == 0,
            },
        )

    @classmethod
    def log_system_config_change(cls, performed_by, change_description: str, request=None) -> None:
        """Fired when a system admin changes platform configuration."""
        _safe_log(
            action=AuditAction.SYSTEM_CONFIG,
            performed_by=performed_by,
            request=request,
            context={"description": change_description[:500]},
        )
