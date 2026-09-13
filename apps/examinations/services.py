"""
apps/examinations/services.py
============================
Official Rwanda Driving Theory Exam Engine & Certification Workflow Service.

Handles:
  1. Dynamic 20-question mock session creation sampled proportionally across official domains.
  2. Answer recording and real-time validation.
  3. Session grading (pass mark: 12/20 = 60%).
  4. Multi-tier review workflow:
     - Board Reviewer evaluation
     - Training Admin pedagogical certification
     - System Admin final approval (Strictly locked until prior stages complete)
     - Automatic Certificate generation with QR code and verification link
     - Single, batch, and whole-cohort result publishing.
"""

import hashlib
import logging
import random
import uuid
from datetime import timedelta
from typing import Any, Dict, List, Optional

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.examinations.models import (
    Certificate,
    CertificateTemplate,
    CertificateTemplateType,
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


# ---------------------------------------------------------------------------
# Certificate Service
# ---------------------------------------------------------------------------

class CertificateService:
    """
    Manages Certificate Templates (Student, Guest, Enterprise) and issues
    verifiable certificates upon System Admin approval.
    """

    @classmethod
    def ensure_default_templates(cls) -> None:
        """Seed default certificate templates if not already present."""
        templates_config = [
            {
                "type": CertificateTemplateType.STUDENT,
                "header_subtitle": "Republic of Rwanda • Sifo Drive Theory Accreditation",
                "title": "Certificate of Theory Competence",
                "conferral_text": "This official credential is proudly awarded to",
                "course_name": "Rwanda Driving Theory — Provisional License Preparation",
                "declaration": (
                    "This is to certify that {student_name} has successfully completed the "
                    "Rwanda Driving Theory Curriculum as part of {cohort_name} (from {start_date} to {completion_date}) "
                    "and demonstrated proficiency in Traffic Regulations, Road Signage, and Highway Code Safety "
                    "with an official certified score of {score}/{total_questions}."
                ),
                "notes": (
                    "Certified in accordance with Rwanda National Police traffic theory regulations and "
                    "Law No 058/2021 on Personal Data Protection. Scan the embedded QR code to verify authenticity."
                ),
                "ta_name": "Ingabire Diane",
                "ta_title": "Head of Training & Pedagogy",
                "dir_name": "Mugabo Eric",
                "dir_title": "Managing Director, Sifo Drive",
            },
            {
                "type": CertificateTemplateType.GUEST,
                "header_subtitle": "Republic of Rwanda • Diagnostic Theory Assessment",
                "title": "Provisional Driving Theory Diagnostic Certificate",
                "conferral_text": "This diagnostic assessment is proudly conferred upon",
                "course_name": "Rwanda Driving Theory Diagnostic Assessment",
                "declaration": (
                    "This is to certify that guest candidate {student_name} sat and completed the "
                    "Rwanda Driving Theory Diagnostic Examination on {completion_date} with an assessed score of "
                    "{score}/{total_questions} ({percentage}%), fulfilling the provisional exam readiness criteria."
                ),
                "notes": (
                    "This certificate represents theory diagnostic evaluation. For full curriculum accreditation, "
                    "enroll in an accredited Sifo Drive cohort. Scan QR code to verify validity."
                ),
                "ta_name": "Ingabire Diane",
                "ta_title": "Examinations Officer",
                "dir_name": "Mugabo Eric",
                "dir_title": "Platform Director",
            },
            {
                "type": CertificateTemplateType.ENTERPRISE,
                "header_subtitle": "Republic of Rwanda • Enterprise Partner Driving Lab",
                "title": "Enterprise Certified Driving Theory Lab Certificate",
                "conferral_text": "This corporate theory certification is proudly conferred upon",
                "course_name": "Rwanda Commercial & Enterprise Driving Safety Theory",
                "declaration": (
                    "This is to certify that {student_name} of {enterprise_name} has successfully completed the "
                    "Enterprise Proctored Driving Theory Examination on {completion_date} (Commenced: {start_date}) "
                    "under certified instructor supervision with an accredited score of {score}/{total_questions}."
                ),
                "notes": (
                    "Certified under accredited driving school partnership with Sifo Drive. Physical attendance "
                    "and proctoring confirmed by instructor of record. Scan QR code to verify official registry."
                ),
                "ta_name": "Ingabire Diane",
                "ta_title": "Enterprise Training Auditor",
                "dir_name": "Mugabo Eric",
                "dir_title": "Director of Operations",
            },
        ]

        for cfg in templates_config:
            CertificateTemplate.objects.get_or_create(
                template_type=cfg["type"],
                defaults={
                    "header_subtitle": cfg["header_subtitle"],
                    "title": cfg["title"],
                    "conferral_text": cfg["conferral_text"],
                    "course_name": cfg["course_name"],
                    "declaration_text": cfg["declaration"],
                    "confirmation_notes": cfg["notes"],
                    "logo_url": "/assets/logo.svg",
                    "training_admin_name": cfg["ta_name"],
                    "training_admin_title": cfg["ta_title"],
                    "training_admin_signature": "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='140' height='40'><path d='M10,25 Q35,5 60,25 T110,20' stroke='%231E90FF' stroke-width='2.5' fill='none'/></svg>",
                    "director_name": cfg["dir_name"],
                    "director_title": cfg["dir_title"],
                    "director_signature": "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='140' height='40'><path d='M10,20 Q40,35 70,10 T120,28' stroke='%23FF2800' stroke-width='2.5' fill='none'/></svg>",
                },
            )

    @classmethod
    @transaction.atomic
    def generate_certificate(cls, session: ExamSession, approver: User) -> Certificate:
        """
        Auto-generates an official Certificate for an approved exam session.
        Applies track-specific date rules and embeds dual signatures and QR code data.
        """
        cls.ensure_default_templates()

        # Check existing certificate
        if hasattr(session, "certificate") and session.certificate:
            return session.certificate

        student = session.student
        role = getattr(student, "role", "STUDENT")

        # Determine track category
        if session.track == "B2B" or role == "ENTERPRISE_ADMIN":
            track_type = CertificateTemplateType.ENTERPRISE
            enterprise_name = getattr(student, "school_name", "") or "Sifo Certified Driving School"
        elif role == "GUEST":
            track_type = CertificateTemplateType.GUEST
            enterprise_name = ""
        else:
            track_type = CertificateTemplateType.STUDENT
            enterprise_name = ""

        # Fetch active template
        template = CertificateTemplate.objects.filter(template_type=track_type, is_active=True).first()
        if not template:
            template = CertificateTemplate.objects.filter(template_type=CertificateTemplateType.STUDENT).first()

        # Date rules
        completion_dt = session.submitted_at or timezone.now()
        start_dt = None
        if track_type != CertificateTemplateType.GUEST:
            if session.cohort and session.cohort.start_date:
                start_dt = timezone.make_aware(
                    timezone.datetime.combine(session.cohort.start_date, timezone.datetime.min.time())
                ) if timezone.is_naive(timezone.datetime.combine(session.cohort.start_date, timezone.datetime.min.time())) else session.cohort.start_date
            else:
                start_dt = student.created_at

        # Serial number: SIFO-CERT-2026-RW-XXXXX
        serial_suffix = uuid.uuid4().hex[:7].upper()
        certificate_no = f"SIFO-CERT-2026-RW-{serial_suffix}"

        # Cryptographic SHA-256 verification hash
        hash_payload = f"{student.id}:{certificate_no}:{session.score}:{completion_dt.isoformat()}:{approver.id}"
        verification_hash = hashlib.sha256(hash_payload.encode()).hexdigest()
        verification_url = f"/verify/certificate/{verification_hash}"

        # Snapshot of template settings at issuance
        snapshot = {
            "template_type": template.template_type if template else track_type,
            "header_subtitle": getattr(template, "header_subtitle", "Republic of Rwanda • Sifo Drive Theory Accreditation") if template else "Republic of Rwanda • Sifo Drive Theory Accreditation",
            "title": template.title if template else "Certificate of Theory Competence",
            "conferral_text": getattr(template, "conferral_text", "This official credential is proudly awarded to") if template else "This official credential is proudly awarded to",
            "course_name": template.course_name if template else "Rwanda Driving Theory",
            "declaration_text": template.declaration_text if template else "",
            "confirmation_notes": template.confirmation_notes if template else "",
            "logo_url": template.logo_url if template else "/assets/logo.svg",
            "training_admin_name": template.training_admin_name if template else "Training Directorate",
            "training_admin_title": template.training_admin_title if template else "Head of Training & Pedagogy",
            "training_admin_signature": template.training_admin_signature if template else "",
            "director_name": template.director_name if template else "Sifo Platform Director",
            "director_title": template.director_title if template else "Managing Director, Sifo Drive",
            "director_signature": template.director_signature if template else "",
            "approved_by_name": approver.get_full_name() or approver.phone_number,
            "approved_by_id": str(approver.id),
        }

        student_code = getattr(student, "student_id", "") or student.phone_number

        cert = Certificate.objects.create(
            certificate_number=certificate_no,
            exam_session=session,
            student=student,
            student_name=student.get_full_name() or student.phone_number,
            student_code=student_code,
            track_type=track_type,
            enterprise_name=enterprise_name,
            started_at=start_dt,
            completed_at=completion_dt,
            score=session.score or 0,
            total_questions=session.total_questions or 20,
            passing_score=session.passing_score,
            passed=session.passed or False,
            verification_hash=verification_hash,
            verification_url=verification_url,
            template_snapshot=snapshot,
            is_valid=True,
        )

        logger.info("Generated Certificate %s for session %s (Student: %s)", certificate_no, session.id, student.id)
        return cert


# ---------------------------------------------------------------------------
# Examination Multi-Tier Review & Publishing Workflow Service
# ---------------------------------------------------------------------------

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
        session.board_reviewer = reviewer
        session.board_reviewed_at = timezone.now()
        session.board_decision = decision.upper()
        session.board_notes = notes

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
            raise ValueError(f"Cannot perform Training Admin review: Session is currently in '{session.status}' stage.")

        session.training_admin = reviewer
        session.training_reviewed_at = timezone.now()
        session.training_decision = decision.upper()
        session.training_notes = notes

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
        session.approval_notes = notes
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
            cert_no = session.certificate.certificate_number if hasattr(session, "certificate") else ""
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
