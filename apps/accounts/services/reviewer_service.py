import logging
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.accounts.constants import UserRole
from apps.accounts.models import ReviewerProfile

User = get_user_model()
logger = logging.getLogger(__name__)


class ReviewerService:
    """Service layer for Board Reviewers and Exam Integrity Examiners."""

    @classmethod
    def get_or_create_profile(cls, user: User) -> ReviewerProfile:
        """Retrieve or initialize a ReviewerProfile for a board reviewer."""
        if user.role != UserRole.BOARD_REVIEWER:
            raise ValueError("Only users with role BOARD_REVIEWER can have a ReviewerProfile.")

        reviewer_code = f"SIFO-REV-{str(user.id)[:6].upper()}"
        profile, created = ReviewerProfile.objects.get_or_create(
            user=user,
            defaults={
                "reviewer_code": reviewer_code,
                "inspector_badge_number": f"INSP-{str(user.id)[:4].upper()}",
            },
        )
        return profile

    @classmethod
    def get_reviewer_dashboard_stats(cls, user: User) -> dict:
        """Aggregate reviewer caseload metrics."""
        profile = cls.get_or_create_profile(user)
        
        # Count exam sessions awaiting board review
        pending_queue_count = 0
        total_reviews = profile.total_reviews_completed
        total_approved = profile.total_certifications_approved
        total_violations = profile.total_violations_confirmed

        try:
            from apps.examinations.models import ExamSession, ExamSessionStatus
            pending_queue_count = ExamSession.objects.filter(
                status__in=[
                    ExamSessionStatus.SUBMITTED,
                    ExamSessionStatus.BOARD_REVIEW,
                    ExamSessionStatus.FLAGGED,
                ],
            ).count()

            # Dynamic tally from session records if present
            session_reviews = ExamSession.objects.filter(board_reviewer=user)
            if session_reviews.exists():
                total_reviews = max(total_reviews, session_reviews.count())
                total_approved = max(total_approved, session_reviews.filter(board_decision="APPROVE").count())
                total_violations = max(total_violations, session_reviews.filter(board_decision="REJECT").count())
        except Exception as e:
            logger.warning("Could not calculate exam session reviewer stats: %s", e)

        return {
            "reviewer_code": profile.reviewer_code,
            "inspector_badge_number": profile.inspector_badge_number,
            "accreditation_authority": profile.accreditation_authority,
            "total_reviews_completed": total_reviews,
            "total_certifications_approved": total_approved,
            "total_violations_confirmed": total_violations,
            "pending_queue_count": pending_queue_count,
            "is_active": profile.is_active_reviewer,
        }

    @classmethod
    def get_flagged_queue(cls) -> list[dict]:
        """Fetch queue of exam sessions awaiting board evaluation or proctoring audit."""
        try:
            from apps.examinations.models import ExamSession, ExamSessionStatus
            sessions = ExamSession.objects.filter(
                status__in=[
                    ExamSessionStatus.SUBMITTED,
                    ExamSessionStatus.BOARD_REVIEW,
                    ExamSessionStatus.FLAGGED,
                ],
            ).select_related("student", "cohort").order_by("-created_at")[:50]

            results = []
            for s in sessions:
                name = s.student.get_full_name() if s.student else "Candidate"
                if not name or not name.strip():
                    name = s.student.phone_number if s.student else "Candidate"

                score_pct = round((s.score / s.total_questions) * 100, 1) if (s.score is not None and s.total_questions) else 0.0
                flag_text = (
                    f"Proctoring Telemetry ({s.violation_count} anomaly logs)"
                    if s.violation_count > 0
                    else "Awaiting Stage 1 Board Certification"
                )

                results.append({
                    "session_id": str(s.id),
                    "candidate_name": name,
                    "candidate_phone": s.student.phone_number if s.student else "",
                    "student_id": getattr(s.student, "student_id", None) if s.student else None,
                    "exam_title": f"Rwanda Driving Theory Mock ({s.track})",
                    "score_percentage": score_pct,
                    "flagged_reason": flag_text,
                    "created_at": s.created_at.isoformat() if s.created_at else None,
                })
            return results
        except Exception as e:
            logger.warning("Could not fetch flagged queue from examinations app: %s", e)
            return []

    @classmethod
    def certify_exam_session(
        cls,
        reviewer_user: User,
        session_id: str,
        action: str,  # 'APPROVE' or 'DISQUALIFY' / 'REJECT'
        remarks: str = "",
    ) -> dict:
        """
        Examiner adjudication: Certify grade or reject session.
        Advances state through ExamWorkflowService and updates examiner records.
        """
        profile = cls.get_or_create_profile(reviewer_user)
        decision = "APPROVE" if action.upper() in ("APPROVE", "CERTIFY") else "REJECT"

        try:
            from apps.examinations.services.workflow_service import ExamWorkflowService
            review_note = remarks.strip() if remarks and remarks.strip() else f"Board evaluation certified by {profile.reviewer_code}"
            session = ExamWorkflowService.board_review_decision(
                session_id=session_id,
                reviewer=reviewer_user,
                decision=decision,
                notes=review_note,
            )

            profile.total_reviews_completed += 1
            if decision == "APPROVE":
                profile.total_certifications_approved += 1
            else:
                profile.total_violations_confirmed += 1
            profile.save(update_fields=[
                "total_reviews_completed",
                "total_certifications_approved",
                "total_violations_confirmed",
            ])

            return {
                "session_id": session_id,
                "status": session.status,
                "adjudicated_by": profile.reviewer_code,
                "message": f"Session marked as {session.status}.",
            }
        except Exception as e:
            logger.error("Error adjudicating exam session %s: %s", session_id, e)
            raise
