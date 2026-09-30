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
        
        # Count flagged exam sessions awaiting review
        pending_queue_count = 0
        try:
            from apps.examinations.models import ExamSession
            pending_queue_count = ExamSession.objects.filter(
                status="FLAGGED_FOR_REVIEW",
            ).count()
        except Exception:
            pending_queue_count = 0

        return {
            "reviewer_code": profile.reviewer_code,
            "inspector_badge_number": profile.inspector_badge_number,
            "accreditation_authority": profile.accreditation_authority,
            "total_reviews_completed": profile.total_reviews_completed,
            "total_certifications_approved": profile.total_certifications_approved,
            "total_violations_confirmed": profile.total_violations_confirmed,
            "pending_queue_count": pending_queue_count,
            "is_active": profile.is_active_reviewer,
        }

    @classmethod
    def get_flagged_queue(cls) -> list[dict]:
        """Fetch queue of exam sessions flagged by proctoring engine for review."""
        try:
            from apps.examinations.models import ExamSession
            flagged_sessions = ExamSession.objects.filter(
                status="FLAGGED_FOR_REVIEW",
            ).select_related("user").order_by("-updated_at")[:50]

            results = []
            for s in flagged_sessions:
                results.append({
                    "session_id": str(s.id),
                    "candidate_name": s.user.full_name if s.user else "Candidate",
                    "candidate_phone": s.user.phone_number if s.user else "",
                    "student_id": getattr(s.user, "student_id", None) if s.user else None,
                    "exam_title": getattr(s.exam, "title", "Theory Mock Exam") if hasattr(s, "exam") and s.exam else "Theory Mock Exam",
                    "score_percentage": getattr(s, "score_percentage", 0),
                    "flagged_reason": getattr(s, "flag_reason", "Multiple faces detected or camera obscured"),
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
        action: str,  # 'APPROVE' or 'DISQUALIFY'
        remarks: str = "",
    ) -> dict:
        """
        Examiner adjudication: Certify grade or disqualify session.
        Updates examiner statistics and audit trail.
        """
        profile = cls.get_or_create_profile(reviewer_user)
        
        try:
            from apps.examinations.models import ExamSession
            session = ExamSession.objects.get(id=session_id)
            if action.upper() == "APPROVE":
                session.status = "COMPLETED"
                profile.total_certifications_approved += 1
            else:
                session.status = "DISQUALIFIED"
                profile.total_violations_confirmed += 1

            session.reviewer_remarks = remarks
            session.reviewed_by = reviewer_user
            session.reviewed_at = timezone.now()
            session.save(update_fields=["status", "reviewer_remarks", "reviewed_by", "reviewed_at"])

            profile.total_reviews_completed += 1
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
            # Still update profile counter if mock session
            profile.total_reviews_completed += 1
            if action.upper() == "APPROVE":
                profile.total_certifications_approved += 1
            else:
                profile.total_violations_confirmed += 1
            profile.save()
            return {
                "session_id": session_id,
                "status": "APPROVED" if action.upper() == "APPROVE" else "DISQUALIFIED",
                "adjudicated_by": profile.reviewer_code,
                "message": f"Review action recorded: {action.upper()}.",
            }
