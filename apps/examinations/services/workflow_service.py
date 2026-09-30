import logging
from typing import Any, Dict, List

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.examinations.models import (
    ExamSession,
    ExamSessionStatus,
)
from apps.examinations.services.certificate_service import CertificateService

logger = logging.getLogger(__name__)


class ExamWorkflowService:
    """
    Orchestrates the strictly sequential review lifecycle:
    SUBMITTED -> BOARD_REVIEW -> TRAINING_REVIEW -> SYSTEM_REVIEW -> APPROVED (Cert Auto-Generated) -> PUBLISHED.
    """

    @classmethod
    @transaction.atomic
    def board_review_decision(
        cls,
        session_id: str,
        reviewer: User,
        decision: str,  # 'APPROVE' or 'REJECT'
        notes: str = "",
    ) -> ExamSession:
        session = ExamSession.objects.get(id=session_id)
        if session.status not in (ExamSessionStatus.SUBMITTED, ExamSessionStatus.BOARD_REVIEW):
            raise ValueError(
                f"Governance Lock: Cannot perform Board Review. Session is currently in '{session.status}' stage."
            )
        if decision.upper() == "APPROVE" and not (notes and notes.strip()):
            raise ValueError("Board review comment is required to approve.")

        session.board_reviewer = reviewer
        session.board_reviewed_at = timezone.now()
        session.board_decision = decision.upper()
        session.board_notes = notes.strip()

        if decision.upper() == "APPROVE":
            session.status = ExamSessionStatus.TRAINING_REVIEW
        else:
            session.status = ExamSessionStatus.REJECTED

        session.save(update_fields=[
            "board_reviewer", "board_reviewed_at", "board_decision", "board_notes", "status", "updated_at"
        ])
        logger.info("Board review on session %s: %s -> %s", session.id, decision, session.status)
        return session

    @classmethod
    @transaction.atomic
    def training_admin_review_decision(
        cls,
        session_id: str,
        reviewer: User,
        decision: str,  # 'APPROVE' or 'REJECT'
        notes: str = "",
    ) -> ExamSession:
        session = ExamSession.objects.get(id=session_id)
        if session.status != ExamSessionStatus.TRAINING_REVIEW:
            raise ValueError(
                f"Governance Lock: Cannot perform Training Admin review: Session is currently in '{session.status}' stage."
            )
        if decision.upper() == "APPROVE" and not (notes and notes.strip()):
            raise ValueError("Training audit comment is required to approve.")

        session.training_admin = reviewer
        session.training_reviewed_at = timezone.now()
        session.training_decision = decision.upper()
        session.training_notes = notes.strip()

        if decision.upper() == "APPROVE":
            session.status = ExamSessionStatus.SYSTEM_REVIEW
        else:
            session.status = ExamSessionStatus.REJECTED

        session.save(update_fields=[
            "training_admin", "training_reviewed_at", "training_decision", "training_notes", "status", "updated_at"
        ])
        logger.info("Training review on session %s: %s -> %s", session.id, decision, session.status)
        return session

    @classmethod
    @transaction.atomic
    def system_admin_approve(
        cls,
        session_id: str,
        system_admin: User,
        notes: str = "",
    ) -> ExamSession:
        """
        Final certification approval by System Administrator.
        Strictly enforces that the exam has passed Training Admin review.
        Auto-generates official Certificate upon approval.
        """
        session = ExamSession.objects.select_related("student", "cohort").get(id=session_id)

        # STRICT SEQUENTIAL GOVERNANCE CHECK:
        if session.status != ExamSessionStatus.SYSTEM_REVIEW:
            raise ValueError(
                f"Governance Lock: Cannot approve exam session in '{session.status}' stage. "
                "The exam must first be reviewed by the Board Reviewer and approved by the Training Administrator."
            )

        session.approved_by = system_admin
        session.approved_at = timezone.now()
        session.approval_notes = notes.strip() if notes else ""
        session.status = ExamSessionStatus.APPROVED
        session.save(update_fields=[
            "approved_by", "approved_at", "approval_notes", "status", "updated_at"
        ])

        # Auto-generate Certificate
        CertificateService.generate_certificate(session, system_admin)
        logger.info("System Admin approved exam %s -> Auto-generated Certificate.", session.id)
        return session

    @classmethod
    @transaction.atomic
    def publish_exam(cls, session_id: str, publisher: User) -> ExamSession:
        """
        Publishes certified exam results to the student dashboard.
        Requires the session to be in APPROVED status.
        """
        session = ExamSession.objects.select_related("student", "certificate").get(id=session_id)
        if session.status != ExamSessionStatus.APPROVED:
            raise ValueError(f"Cannot publish: Session must be in APPROVED status (currently '{session.status}').")

        session.is_published = True
        session.published_by = publisher
        session.published_at = timezone.now()
        session.status = ExamSessionStatus.PUBLISHED
        session.save(update_fields=["is_published", "published_by", "published_at", "status", "updated_at"])

        # Optional: Notify student via notification service
        try:
            from apps.notifications.services import NotificationService
            NotificationService.send_exam_result(
                user=session.student,
                score=session.score or 0,
                max_score=session.total_questions or 20,
                passed=session.passed or False,
                exam_id=str(session.id),
            )
        except Exception as exc:
            logger.warning("Could not dispatch notification for published exam %s: %s", session.id, exc)

        logger.info("Published exam session %s by %s.", session.id, publisher.id)
        return session

    @classmethod
    @transaction.atomic
    def publish_batch(cls, session_ids: List[str], publisher: User) -> Dict[str, Any]:
        """Publish a list of approved exam sessions."""
        sessions = ExamSession.objects.filter(id__in=session_ids, status=ExamSessionStatus.APPROVED)
        published_count = 0
        for session in sessions:
            cls.publish_exam(str(session.id), publisher)
            published_count += 1

        return {
            "requested_count": len(session_ids),
            "published_count": published_count,
        }

    @classmethod
    @transaction.atomic
    def publish_cohort(cls, cohort_id: str, publisher: User) -> Dict[str, Any]:
        """Publish all approved exam sessions belonging to a specific cohort."""
        approved_sessions = list(
            ExamSession.objects.filter(
                cohort_id=cohort_id,
                status=ExamSessionStatus.APPROVED,
            ).values_list("id", flat=True)
        )

        result = cls.publish_batch([str(sid) for sid in approved_sessions], publisher)
        result["cohort_id"] = cohort_id
        return result
