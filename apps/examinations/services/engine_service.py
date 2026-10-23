"""
apps/examinations/services/engine_service.py
============================================
Core domain logic for driving theory exam sessions.
Guarantees:
  - 20 questions randomly sampled across official domains:
      Priority: 4, Signage: 4, Speed: 4, Legal: 3, Safety: 3, Parking: 2
  - Exact 20-minute server countdown
  - 1 point per question, passing mark: 12/20
  - Frozen question snapshot on every attempt (edits never alter past exams)
  - Auto-grading and score immutability (not even System Admin can edit)
  - Student exams route to Board Review; Guest & Public exams route to instant results
"""

import json
import logging
import os
import random
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from django.conf import settings
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

PARSED_QUESTIONS_FILE = os.path.join(settings.BASE_DIR, "data", "parsed_questions.json")
SESSIONS_BACKUP_FILE = os.path.join(settings.BASE_DIR, "data", "exam_sessions.json")


class ExamEngineService:
    """Core domain logic for driving theory exam sessions."""

    DOMAIN_DISTRIBUTION = {
        "PRIORITY": 4,
        "SIGNAGE": 4,
        "SPEED": 4,
        "LEGAL": 3,
        "SAFETY": 3,
        "PARKING": 2,
    }

    TOTAL_QUESTIONS = 20
    DURATION_MINUTES = 20
    PASSING_SCORE = 12
    POINTS_PER_QUESTION = 1

    @classmethod
    def _load_questions_pool_from_file(cls) -> List[Dict[str, Any]]:
        """Fallback question pool loader from data/parsed_questions.json."""
        if not os.path.exists(PARSED_QUESTIONS_FILE):
            return []
        try:
            with open(PARSED_QUESTIONS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else data.get("questions", [])
        except Exception as e:
            logger.error("Failed to load parsed questions from file: %s", e)
            return []

    @classmethod
    def sample_20_questions(cls) -> List[Dict[str, Any]]:
        """
        Pulls exactly 20 random questions following the domain distribution:
        Priority: 4, Signage: 4, Speed: 4, Legal: 3, Safety: 3, Parking: 2.
        No duplicates within the same attempt.
        """
        # Try database first
        db_available = False
        try:
            if QuizQuestion.objects.filter(is_active=True, is_deleted=False).exists():
                db_available = True
        except Exception:
            db_available = False

        if db_available:
            selected_items = []
            selected_ids = set()

            for domain_str, count in cls.DOMAIN_DISTRIBUTION.items():
                domain_val = getattr(QuizDomain, domain_str, domain_str)
                pool = list(
                    QuizQuestion.objects.filter(
                        domain=domain_val,
                        is_active=True,
                        is_deleted=False,
                    ).exclude(id__in=selected_ids)
                )
                sampled = random.sample(pool, min(len(pool), count))
                for q in sampled:
                    selected_ids.add(q.id)
                    selected_items.append(cls._serialize_quiz_question(q))

            if len(selected_items) < cls.TOTAL_QUESTIONS:
                needed = cls.TOTAL_QUESTIONS - len(selected_items)
                backfill_pool = list(
                    QuizQuestion.objects.filter(
                        is_active=True,
                        is_deleted=False,
                    ).exclude(id__in=selected_ids)
                )
                if backfill_pool:
                    extra = random.sample(backfill_pool, min(len(backfill_pool), needed))
                    for q in extra:
                        selected_ids.add(q.id)
                        selected_items.append(cls._serialize_quiz_question(q))

            random.shuffle(selected_items)
            return selected_items

        # Fallback to parsed_questions.json
        file_pool = cls._load_questions_pool_from_file()
        if not file_pool:
            return []

        selected_items = []
        selected_numbers = set()

        for domain_str, count in cls.DOMAIN_DISTRIBUTION.items():
            domain_pool = [
                q for q in file_pool
                if q.get("domain") == domain_str and q.get("question_number") not in selected_numbers
            ]
            sampled = random.sample(domain_pool, min(len(domain_pool), count))
            for q in sampled:
                selected_numbers.add(q.get("question_number"))
                selected_items.append(cls._normalize_question_dict(q))

        if len(selected_items) < cls.TOTAL_QUESTIONS:
            needed = cls.TOTAL_QUESTIONS - len(selected_items)
            backfill = [
                q for q in file_pool
                if q.get("question_number") not in selected_numbers
            ]
            if backfill:
                extra = random.sample(backfill, min(len(backfill), needed))
                for q in extra:
                    selected_numbers.add(q.get("question_number"))
                    selected_items.append(cls._normalize_question_dict(q))

        random.shuffle(selected_items)
        return selected_items

    @staticmethod
    def _serialize_quiz_question(q: QuizQuestion) -> Dict[str, Any]:
        return {
            "id": str(q.id),
            "question_number": q.question_number,
            "domain": q.domain,
            "question_text": q.question_text,
            "question_text_kinyarwanda": q.question_text_kinyarwanda,
            "question_text_french": q.question_text_french or "",
            "option_a": q.option_a,
            "option_b": q.option_b,
            "option_c": q.option_c,
            "option_d": q.option_d,
            "option_a_kinyarwanda": q.option_a_kinyarwanda,
            "option_b_kinyarwanda": q.option_b_kinyarwanda,
            "option_c_kinyarwanda": q.option_c_kinyarwanda,
            "option_d_kinyarwanda": q.option_d_kinyarwanda,
            "option_a_french": q.option_a_french or "",
            "option_b_french": q.option_b_french or "",
            "option_c_french": q.option_c_french or "",
            "option_d_french": q.option_d_french or "",
            "correct_option": q.correct_option,
            "explanation": q.explanation or "",
            "explanation_kinyarwanda": q.explanation_kinyarwanda or "",
            "explanation_french": q.explanation_french or "",
            "image": q.image.url if getattr(q, "image", None) and hasattr(q.image, "url") else None,
        }

    @staticmethod
    def _normalize_question_dict(q: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": str(q.get("id", q.get("question_number", ""))),
            "question_number": q.get("question_number"),
            "domain": q.get("domain", "GENERAL"),
            "question_text": q.get("question_text", ""),
            "question_text_kinyarwanda": q.get("question_text_kinyarwanda", ""),
            "question_text_french": q.get("question_text_french", ""),
            "option_a": q.get("option_a", ""),
            "option_b": q.get("option_b", ""),
            "option_c": q.get("option_c", ""),
            "option_d": q.get("option_d", ""),
            "option_a_kinyarwanda": q.get("option_a_kinyarwanda", ""),
            "option_b_kinyarwanda": q.get("option_b_kinyarwanda", ""),
            "option_c_kinyarwanda": q.get("option_c_kinyarwanda", ""),
            "option_d_kinyarwanda": q.get("option_d_kinyarwanda", ""),
            "option_a_french": q.get("option_a_french", ""),
            "option_b_french": q.get("option_b_french", ""),
            "option_c_french": q.get("option_c_french", ""),
            "option_d_french": q.get("option_d_french", ""),
            "correct_option": (q.get("correct_option") or "A").strip().upper(),
            "explanation": q.get("explanation", ""),
            "explanation_kinyarwanda": q.get("explanation_kinyarwanda", ""),
            "explanation_french": q.get("explanation_french", ""),
            "image": q.get("image"),
        }

    @classmethod
    def start_exam_session(
        cls,
        student: Any,
        exam_id: Optional[str] = None,
        track: str = "STUDENT",
        duration_minutes: int = 20,
        student_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Initiates a 20-minute exam attempt with 20 fresh randomly pulled questions.
        Saves frozen question payload to guarantee historical immutability.
        """
        now = timezone.now()
        expires_at = now + timedelta(minutes=duration_minutes)

        sampled_questions = cls.sample_20_questions()
        if len(sampled_questions) < cls.TOTAL_QUESTIONS:
            logger.warning("Sampled %d questions instead of 20.", len(sampled_questions))

        # Build session question items with frozen data
        session_questions_data = []
        for seq, q_payload in enumerate(sampled_questions):
            session_questions_data.append({
                "sequence_number": seq + 1,
                "selected_option": "",
                "is_correct": None,
                "answered_at": None,
                "frozen_data": q_payload,
            })

        session_id = str(uuid.uuid4())
        user_id = str(getattr(student, "id", student))
        from apps.examinations.services.credit_service import ExamCreditService
        user_name = (
            student_name
            or getattr(student, "full_name", None)
            or ExamCreditService.get_candidate_name(user_id)
            or "Candidate"
        )

        session_obj = {
            "id": session_id,
            "student_id": user_id,
            "student_name": user_name,
            "exam_id": str(exam_id) if exam_id else None,
            "track": track,
            "status": "ACTIVE",
            "started_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "submitted_at": None,
            "duration_minutes": duration_minutes,
            "score": None,
            "total_questions": len(session_questions_data),
            "passing_score": cls.PASSING_SCORE,
            "passed": None,
            "violation_count": 0,
            "session_questions": session_questions_data,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        # Backup save to sessions file
        cls._save_session_record(session_obj)

        logger.info(
            "Created ExamSession %s for user %s (track=%s) with %d questions.",
            session_id, user_id, track, len(session_questions_data)
        )
        return session_obj

    @classmethod
    def _save_session_record(cls, session_dict: Dict[str, Any]) -> None:
        try:
            os.makedirs(os.path.dirname(SESSIONS_BACKUP_FILE), exist_ok=True)
            sessions = []
            if os.path.exists(SESSIONS_BACKUP_FILE):
                try:
                    with open(SESSIONS_BACKUP_FILE, "r", encoding="utf-8") as f:
                        sessions = json.load(f)
                except Exception:
                    sessions = []

            # Replace or append
            replaced = False
            for idx, s in enumerate(sessions):
                if str(s.get("id")) == str(session_dict.get("id")):
                    sessions[idx] = session_dict
                    replaced = True
                    break
            if not replaced:
                sessions.insert(0, session_dict)

            temp = f"{SESSIONS_BACKUP_FILE}.tmp"
            with open(temp, "w", encoding="utf-8") as f:
                json.dump(sessions, f, indent=2, ensure_ascii=False)
            os.replace(temp, SESSIONS_BACKUP_FILE)
        except Exception as e:
            logger.error("Failed saving session record %s: %s", session_dict.get("id"), e)

    @classmethod
    def get_session(cls, session_id: str) -> Optional[Dict[str, Any]]:
        if not os.path.exists(SESSIONS_BACKUP_FILE):
            return None
        try:
            with open(SESSIONS_BACKUP_FILE, "r", encoding="utf-8") as f:
                sessions = json.load(f)
                for s in sessions:
                    if str(s.get("id")) == str(session_id):
                        return s
        except Exception:
            return None
        return None

    @classmethod
    def record_answer(cls, session_id: str, sequence_number: int, selected_option: str) -> Dict[str, Any]:
        session = cls.get_session(session_id)
        if not session:
            raise ValueError(f"Exam session {session_id} not found.")

        if session.get("status") != "ACTIVE":
            raise ValueError(f"Cannot record answer: Session status is '{session.get('status')}'.")

        now = timezone.now()
        expires_at_str = session.get("expires_at")
        if expires_at_str:
            expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
            if now > expires_at:
                session["status"] = "EXPIRED"
                cls._save_session_record(session)
                raise ValueError("Exam session time limit (20 min) has expired.")

        clean_opt = (selected_option or "").strip().upper()
        if clean_opt not in ("A", "B", "C", "D"):
            raise ValueError("Invalid answer option. Must be A, B, C, or D.")

        questions = session.get("session_questions", [])
        target_q = None
        for q in questions:
            if q.get("sequence_number") == sequence_number:
                target_q = q
                break

        if not target_q:
            raise ValueError(f"Question #{sequence_number} not found in this exam session.")

        target_q["selected_option"] = clean_opt
        target_q["answered_at"] = now.isoformat()
        correct_opt = (target_q.get("frozen_data", {}).get("correct_option") or "").strip().upper()
        target_q["is_correct"] = (clean_opt == correct_opt)

        session["updated_at"] = now.isoformat()
        cls._save_session_record(session)
        return target_q

    @classmethod
    def grade_session(cls, session_id: str) -> Dict[str, Any]:
        """
        Auto-grades the 20-question session.
        Grades are immutable once computed.
        """
        session = cls.get_session(session_id)
        if not session:
            raise ValueError(f"Exam session {session_id} not found.")

        # If already graded, return immutable result
        if session.get("score") is not None and session.get("status") not in ("ACTIVE", "EXPIRED"):
            return session

        now = timezone.now()
        questions = session.get("session_questions", [])
        correct_count = 0

        for q in questions:
            selected = (q.get("selected_option") or "").strip().upper()
            correct_opt = (q.get("frozen_data", {}).get("correct_option") or "").strip().upper()
            is_correct = (selected == correct_opt) and bool(selected)
            q["is_correct"] = is_correct
            if is_correct:
                correct_count += cls.POINTS_PER_QUESTION

        session["score"] = correct_count
        session["passed"] = (correct_count >= cls.PASSING_SCORE)
        session["submitted_at"] = now.isoformat()

        track = (session.get("track") or "STUDENT").upper()
        if track in ("STUDENT", "B2B"):
            # Enters Stage 1 Board Review for proctored student accreditation
            session["status"] = "BOARD_REVIEW"
        else:
            # Guest & Public candidates get instant published results
            session["status"] = "PUBLISHED"
            session["is_published"] = True
            session["published_at"] = now.isoformat()

        session["updated_at"] = now.isoformat()
        cls._save_session_record(session)

        logger.info(
            "Graded ExamSession %s: Score %d/%d (Passed: %s) -> Status: %s",
            session_id, correct_count, len(questions), session["passed"], session["status"]
        )
        return session

    @classmethod
    def record_proctoring_event(
        cls,
        session_id: str,
        event_type: str,
        snapshot_image: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        is_violation: bool = True,
    ) -> Dict[str, Any]:
        """
        Logs proctoring telemetry (tab switch, window blur, webcam snapshot, microphone spike).
        Increments violation counter when violation is flagged.
        """
        session = cls.get_session(session_id)
        if not session:
            raise ValueError(f"Exam session {session_id} not found.")

        now = timezone.now()
        event_id = str(uuid.uuid4())
        event_obj = {
            "id": event_id,
            "session_id": session_id,
            "event_type": event_type,
            "snapshot_image": snapshot_image or "",
            "metadata": metadata or {},
            "is_violation": is_violation,
            "created_at": now.isoformat(),
        }

        if "proctoring_events" not in session:
            session["proctoring_events"] = []

        session["proctoring_events"].append(event_obj)
        if is_violation:
            session["violation_count"] = session.get("violation_count", 0) + 1

        session["updated_at"] = now.isoformat()
        cls._save_session_record(session)

        # Also attempt DB persist if active
        try:
            from apps.examinations.models import ExamSession, ProctoringEvent
            db_session = ExamSession.objects.filter(id=session_id).first()
            if db_session:
                ProctoringEvent.objects.create(
                    session=db_session,
                    event_type=event_type,
                    snapshot_image=snapshot_image or "",
                    metadata=metadata or {},
                    is_violation=is_violation,
                )
                if is_violation:
                    db_session.violation_count += 1
                    db_session.save(update_fields=["violation_count", "updated_at"])
        except Exception as e:
            logger.debug("Database proctoring event create skipped: %s", e)

        return event_obj

    @classmethod
    def record_preflight_identity(
        cls,
        session_id: str,
        selfie_image: str,
        preflight_checks: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Stores pre-flight identity snapshot and hardware diagnostics.
        """
        session = cls.get_session(session_id)
        if not session:
            return

        session["identity_image"] = selfie_image
        session["preflight_checks"] = preflight_checks or {}
        session["updated_at"] = timezone.now().isoformat()

        # Add as IDENTITY_CHECK proctoring event
        if selfie_image:
            cls.record_proctoring_event(
                session_id=session_id,
                event_type="IDENTITY_CHECK",
                snapshot_image=selfie_image,
                metadata={"type": "preflight_selfie", "checks": preflight_checks or {}},
                is_violation=False,
            )

        cls._save_session_record(session)

    @classmethod
    def get_student_attempt_for_exam(cls, student_id: str, exam_id: str) -> Optional[Dict[str, Any]]:
        """
        Finds the student's attempt for a specific scheduled exam.
        Enforces 1 attempt policy.
        """
        sessions = []
        if os.path.exists(SESSIONS_BACKUP_FILE):
            try:
                with open(SESSIONS_BACKUP_FILE, "r", encoding="utf-8") as f:
                    sessions = json.load(f)
            except Exception:
                sessions = []

        for s in sessions:
            if str(s.get("student_id")) == str(student_id) and str(s.get("exam_id")) == str(exam_id):
                return s
        return None

    @classmethod
    def list_student_available_exams(cls, student: Any) -> List[Dict[str, Any]]:
        """
        Lists official scheduled exams available for an enrolled student.
        Attaches the student's attempt status, session ID, and grade details.
        """
        from apps.examinations.services.exam_service import ExamService
        all_exams = ExamService.list_exams(exam_type="STUDENT", status="PUBLISHED")

        student_id = str(getattr(student, "id", student))
        enrolled_cohort_ids = set()
        try:
            if hasattr(student, "enrolled_cohorts"):
                enrolled_cohort_ids = {str(c.id) for c in student.enrolled_cohorts.all()}
        except Exception:
            enrolled_cohort_ids = set()

        now = timezone.now()
        results = []

        for exam in all_exams:
            exam_id = str(exam.get("id"))
            cohort_id = exam.get("cohort_id")

            # If exam is restricted to a cohort, verify student enrollment
            if cohort_id and enrolled_cohort_ids and str(cohort_id) not in enrolled_cohort_ids:
                continue

            # Calculate window status
            open_date_str = exam.get("open_date")
            closing_date_str = exam.get("closing_date")

            is_open = True
            is_upcoming = False
            is_closed = False

            if open_date_str:
                try:
                    open_dt = datetime.fromisoformat(open_date_str.replace("Z", "+00:00"))
                    if now < open_dt:
                        is_open = False
                        is_upcoming = True
                except Exception:
                    pass

            if closing_date_str:
                try:
                    close_dt = datetime.fromisoformat(closing_date_str.replace("Z", "+00:00"))
                    if now > close_dt:
                        is_open = False
                        is_closed = True
                except Exception:
                    pass

            attempt = cls.get_student_attempt_for_exam(student_id, exam_id)
            attempt_info = {
                "has_attempt": bool(attempt),
                "attempt_id": attempt.get("id") if attempt else None,
                "status": attempt.get("status") if attempt else "NOT_STARTED",
                "score": attempt.get("score") if attempt else None,
                "passed": attempt.get("passed") if attempt else None,
                "total_questions": 20,
                "passing_score": cls.PASSING_SCORE,
                "time_remaining_seconds": 0,
            }

            if attempt and attempt.get("status") == "ACTIVE":
                expires_at_str = attempt.get("expires_at")
                if expires_at_str:
                    try:
                        expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
                        rem = (expires_at - now).total_seconds()
                        if rem <= 0:
                            # Auto grade expired session
                            cls.grade_session(attempt["id"])
                            attempt = cls.get_session(attempt["id"])
                            attempt_info["status"] = attempt.get("status", "BOARD_REVIEW")
                            attempt_info["score"] = attempt.get("score")
                            attempt_info["passed"] = attempt.get("passed")
                        else:
                            attempt_info["time_remaining_seconds"] = max(0, int(rem))
                    except Exception:
                        pass

            item = dict(exam)
            item["window_status"] = "UPCOMING" if is_upcoming else ("CLOSED" if is_closed else "OPEN")
            item["can_start"] = (is_open and (not attempt or attempt.get("status") == "ACTIVE"))
            item["attempt"] = attempt_info
            results.append(item)

        return results

    @classmethod
    def list_all_sessions(
        cls,
        cohort_id: Optional[str] = None,
        stage: Optional[str] = None,
        track: Optional[str] = None,
        search: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Lists all exam sessions with file fallback.
        """
        sessions = []
        if os.path.exists(SESSIONS_BACKUP_FILE):
            try:
                with open(SESSIONS_BACKUP_FILE, "r", encoding="utf-8") as f:
                    sessions = json.load(f)
            except Exception:
                sessions = []

        results = []
        search_lower = (search or "").strip().lower()

        for s in sessions:
            if stage and stage.upper() != "ALL" and s.get("status") != stage.upper():
                continue
            if track and track.upper() != "ALL" and (s.get("track") or "").upper() != track.upper():
                continue
            if cohort_id and cohort_id != "ALL" and str(s.get("cohort_id")) != str(cohort_id):
                continue
            if search_lower:
                s_name = (s.get("student_name") or "").lower()
                s_id = str(s.get("student_id") or "").lower()
                if search_lower not in s_name and search_lower not in s_id:
                    continue

            results.append(s)

        # Sort by updated_at or created_at desc
        results.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return results

    @classmethod
    def update_session_stage_action(
        cls,
        session_id: str,
        action: str,
        decision: str,
        notes: str,
        reviewer_user: Any,
    ) -> Dict[str, Any]:
        """
        Updates session review stage in fallback storage and enforces sequential governance.
        """
        session = cls.get_session(session_id)
        if not session:
            raise ValueError(f"Exam session {session_id} not found.")

        now = timezone.now().isoformat()
        current_status = session.get("status")
        rev_name = getattr(reviewer_user, "full_name", None) or getattr(reviewer_user, "phone_number", None) or "Admin"

        if action == "BOARD_DECISION":
            if current_status not in ("SUBMITTED", "BOARD_REVIEW"):
                raise ValueError(f"Cannot perform Board Review in stage '{current_status}'.")
            session["board_decision"] = decision.upper()
            session["board_notes"] = notes
            session["board_reviewed_at"] = now
            session["board_reviewer_name"] = rev_name
            session["status"] = "TRAINING_REVIEW" if decision.upper() == "APPROVE" else "REJECTED"

        elif action == "TRAINING_DECISION":
            if current_status != "TRAINING_REVIEW":
                raise ValueError(f"Cannot perform Training Audit in stage '{current_status}'.")
            session["training_decision"] = decision.upper()
            session["training_notes"] = notes
            session["training_reviewed_at"] = now
            session["training_admin_name"] = rev_name
            session["status"] = "SYSTEM_REVIEW" if decision.upper() == "APPROVE" else "REJECTED"

        elif action == "SYSTEM_APPROVE":
            if current_status != "SYSTEM_REVIEW":
                raise ValueError(f"Cannot execute final System Admin approval in stage '{current_status}'.")
            session["approved_by_name"] = rev_name
            session["approval_notes"] = notes
            session["approved_at"] = now
            session["status"] = "APPROVED"
            # Auto-assign certificate info
            session["has_certificate"] = True
            session["certificate_number"] = f"CERT-SD-{random.randint(100000, 999999)}"

        elif action == "REJECT":
            session["status"] = "REJECTED"
            session["approval_notes"] = notes

        session["updated_at"] = now
        cls._save_session_record(session)
        return session

    @classmethod
    def publish_session_fallback(cls, session_id: str, publisher_user: Any) -> Dict[str, Any]:
        session = cls.get_session(session_id)
        if not session:
            raise ValueError(f"Exam session {session_id} not found.")
        now = timezone.now().isoformat()
        pub_name = getattr(publisher_user, "full_name", None) or "System Admin"
        session["is_published"] = True
        session["published_by_name"] = pub_name
        session["published_at"] = now
        session["status"] = "PUBLISHED"
        session["updated_at"] = now
        cls._save_session_record(session)
        return session

