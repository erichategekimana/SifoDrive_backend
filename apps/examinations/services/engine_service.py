import logging
import random
from datetime import timedelta
from typing import Optional

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.examinations.models import (
    ExamSession,
    ExamSessionStatus,
    ProctoringEvent,
    SessionQuestion,
)
from apps.lms.models import QuizDomain, QuizQuestion

logger = logging.getLogger(__name__)


class ExamEngineService:
    """Core domain logic for driving theory exam sessions."""

    DOMAIN_DISTRIBUTION = {
        QuizDomain.PRIORITY: 4,
        QuizDomain.SIGNAGE:  4,
        QuizDomain.SPEED:    4,
        QuizDomain.LEGAL:    3,
        QuizDomain.SAFETY:   3,
        QuizDomain.PARKING:  2,
    }

    @classmethod
    @transaction.atomic
    def start_exam_session(cls, student: User, track: str = "B2C", duration_minutes: int = 20) -> ExamSession:
        """
        Creates a new ExamSession for a student with 20 randomly sampled questions.
        Automatically associates student's enrolled cohort if present.
        """
        now = timezone.now()
        expires_at = now + timedelta(minutes=duration_minutes)

        cohort = None
        if hasattr(student, "enrolled_cohorts"):
            cohort = student.enrolled_cohorts.first()

        session = ExamSession.objects.create(
            student=student,
            cohort=cohort,
            track=track,
            status=ExamSessionStatus.ACTIVE,
            started_at=now,
            expires_at=expires_at,
            total_questions=20,
        )

        selected_questions = []
        selected_ids = set()

        for domain, count in cls.DOMAIN_DISTRIBUTION.items():
            pool = list(
                QuizQuestion.objects.filter(
                    domain=domain,
                    is_active=True,
                    is_deleted=False,
                ).exclude(id__in=selected_ids).values_list("id", flat=True)
            )
            sampled = random.sample(pool, min(len(pool), count))
            selected_ids.update(sampled)
            selected_questions.extend(sampled)

        if len(selected_questions) < 20:
            remaining_needed = 20 - len(selected_questions)
            backfill_pool = list(
                QuizQuestion.objects.filter(
                    is_active=True,
                    is_deleted=False,
                ).exclude(id__in=selected_ids).values_list("id", flat=True)
            )
            if backfill_pool:
                extra = random.sample(backfill_pool, min(len(backfill_pool), remaining_needed))
                selected_questions.extend(extra)

        random.shuffle(selected_questions)

        session_questions = [
            SessionQuestion(
                session=session,
                question_id=q_id,
                sequence_number=seq + 1,
            )
            for seq, q_id in enumerate(selected_questions)
        ]
        SessionQuestion.objects.bulk_create(session_questions)

        logger.info("Created ExamSession %s for user %s with %d questions.", session.id, student.id, len(session_questions))
        return session

    @classmethod
    def record_answer(cls, session: ExamSession, sequence_number: int, selected_option: str) -> SessionQuestion:
        if session.status != ExamSessionStatus.ACTIVE:
            raise ValueError(f"Cannot record answer: Session status is '{session.status}'.")

        if timezone.now() > session.expires_at:
            session.status = ExamSessionStatus.EXPIRED
            session.save(update_fields=["status", "updated_at"])
            raise ValueError("Exam session time limit exceeded.")

        session_q = session.session_questions.select_related("question").get(sequence_number=sequence_number)
        clean_opt = selected_option.strip().upper()
        if clean_opt not in ("A", "B", "C", "D"):
            raise ValueError("Invalid answer option. Must be A, B, C, or D.")

        session_q.selected_option = clean_opt
        session_q.is_correct = (clean_opt == session_q.question.correct_option)
        session_q.answered_at = timezone.now()
        session_q.save(update_fields=["selected_option", "is_correct", "answered_at", "updated_at"])
        return session_q

    @classmethod
    @transaction.atomic
    def grade_session(cls, session: ExamSession) -> ExamSession:
        now = timezone.now()
        questions = list(session.session_questions.select_related("question"))

        correct_count = 0
        for sq in questions:
            if sq.selected_option:
                sq.is_correct = (sq.selected_option.upper() == sq.question.correct_option.upper())
                if sq.is_correct:
                    correct_count += 1
            else:
                sq.is_correct = False
            sq.save(update_fields=["is_correct", "updated_at"])

        session.score = correct_count
        session.passed = (correct_count >= session.passing_score)
        session.submitted_at = now
        # When submitted, exam enters Board Review stage
        session.status = ExamSessionStatus.BOARD_REVIEW
        session.save(update_fields=["score", "passed", "status", "submitted_at", "updated_at"])

        logger.info("Graded ExamSession %s: Score %d/%d (Passed: %s) -> BOARD_REVIEW", session.id, correct_count, len(questions), session.passed)
        return session

    @classmethod
    def record_proctoring_event(
        cls,
        session: ExamSession,
        event_type: str,
        metadata: Optional[dict] = None,
        is_violation: bool = False,
    ) -> ProctoringEvent:
        event = ProctoringEvent.objects.create(
            session=session,
            event_type=event_type,
            metadata=metadata or {},
            is_violation=is_violation,
        )
        if is_violation:
            session.violation_count += 1
            if session.violation_count >= 3 and session.status == ExamSessionStatus.ACTIVE:
                session.status = ExamSessionStatus.FLAGGED
            session.save(update_fields=["violation_count", "status", "updated_at"])

        return event
