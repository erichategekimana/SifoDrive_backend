"""
apps/examinations/views/candidate_views.py
==========================================
Candidate-facing API Views for:
  1. Enrolled Students taking scheduled proctored exams (single-attempt, 20-min countdown, proctoring telemetry).
  2. Guest & Public candidates purchasing mock exams via MoMo, consuming credits, and getting instant auto-graded results.
  3. Post-submission answer and explanation review for all candidates.
"""

import logging
from datetime import datetime
from typing import Any, Dict
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView

from apps.core.mixins import SuccessResponseMixin
from apps.examinations.serializers import (
    BuyExamPackageSerializer,
    CandidateSessionResultSerializer,
    CandidateSessionStateSerializer,
    ProctorEventInputSerializer,
    RecordAnswerSerializer,
    StartStudentExamSerializer,
)
from apps.examinations.services import (
    ExamCreditService,
    ExamEngineService,
    ExamService,
)

logger = logging.getLogger(__name__)


def _format_active_session(session: Dict[str, Any]) -> Dict[str, Any]:
    """Formats active exam session for the runner interface without leaking answer keys."""
    now = timezone.now()
    expires_at_str = session.get("expires_at", "")
    time_remaining = 0
    if expires_at_str:
        try:
            expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
            time_remaining = max(0, int((expires_at - now).total_seconds()))
        except Exception:
            time_remaining = 0

    session_questions = session.get("session_questions", [])
    formatted_questions = []
    answered_count = 0

    for q in session_questions:
        frozen = q.get("frozen_data", {})
        selected = q.get("selected_option", "")
        if selected:
            answered_count += 1

        formatted_questions.append({
            "sequence_number": q.get("sequence_number"),
            "selected_option": selected,
            "answered_at": q.get("answered_at"),
            "id": str(frozen.get("id", q.get("sequence_number"))),
            "question_number": frozen.get("question_number", q.get("sequence_number")),
            "domain": frozen.get("domain", "GENERAL"),
            "question_text": frozen.get("question_text", ""),
            "question_text_kinyarwanda": frozen.get("question_text_kinyarwanda", ""),
            "question_text_french": frozen.get("question_text_french", ""),
            "option_a": frozen.get("option_a", ""),
            "option_b": frozen.get("option_b", ""),
            "option_c": frozen.get("option_c", ""),
            "option_d": frozen.get("option_d", ""),
            "option_a_kinyarwanda": frozen.get("option_a_kinyarwanda", ""),
            "option_b_kinyarwanda": frozen.get("option_b_kinyarwanda", ""),
            "option_c_kinyarwanda": frozen.get("option_c_kinyarwanda", ""),
            "option_d_kinyarwanda": frozen.get("option_d_kinyarwanda", ""),
            "option_a_french": frozen.get("option_a_french", ""),
            "option_b_french": frozen.get("option_b_french", ""),
            "option_c_french": frozen.get("option_c_french", ""),
            "option_d_french": frozen.get("option_d_french", ""),
            "image": frozen.get("image"),
        })

    # Retrieve exam title if available
    exam_title = "Official Rwanda Traffic Theory Examination"
    exam_id = session.get("exam_id")
    if exam_id:
        exam = ExamService.get_exam(str(exam_id))
        if exam:
            exam_title = exam.get("title", exam_title)

    return {
        "id": session.get("id"),
        "exam_id": exam_id,
        "exam_title": exam_title,
        "track": session.get("track", "STUDENT"),
        "status": session.get("status", "ACTIVE"),
        "started_at": session.get("started_at"),
        "expires_at": session.get("expires_at"),
        "duration_minutes": session.get("duration_minutes", 20),
        "time_remaining_seconds": time_remaining,
        "total_questions": len(formatted_questions),
        "answered_count": answered_count,
        "violation_count": session.get("violation_count", 0),
        "questions": formatted_questions,
    }


def _format_results_session(session: Dict[str, Any]) -> Dict[str, Any]:
    """Formats completed/graded exam session with full answer keys and rationale."""
    session_questions = session.get("session_questions", [])
    formatted_questions = []

    for q in session_questions:
        frozen = q.get("frozen_data", {})
        formatted_questions.append({
            "sequence_number": q.get("sequence_number"),
            "selected_option": q.get("selected_option", ""),
            "answered_at": q.get("answered_at"),
            "id": str(frozen.get("id", q.get("sequence_number"))),
            "question_number": frozen.get("question_number", q.get("sequence_number")),
            "domain": frozen.get("domain", "GENERAL"),
            "question_text": frozen.get("question_text", ""),
            "question_text_kinyarwanda": frozen.get("question_text_kinyarwanda", ""),
            "question_text_french": frozen.get("question_text_french", ""),
            "option_a": frozen.get("option_a", ""),
            "option_b": frozen.get("option_b", ""),
            "option_c": frozen.get("option_c", ""),
            "option_d": frozen.get("option_d", ""),
            "option_a_kinyarwanda": frozen.get("option_a_kinyarwanda", ""),
            "option_b_kinyarwanda": frozen.get("option_b_kinyarwanda", ""),
            "option_c_kinyarwanda": frozen.get("option_c_kinyarwanda", ""),
            "option_d_kinyarwanda": frozen.get("option_d_kinyarwanda", ""),
            "option_a_french": frozen.get("option_a_french", ""),
            "option_b_french": frozen.get("option_b_french", ""),
            "option_c_french": frozen.get("option_c_french", ""),
            "option_d_french": frozen.get("option_d_french", ""),
            "image": frozen.get("image"),
            "correct_option": (frozen.get("correct_option") or "A").strip().upper(),
            "is_correct": q.get("is_correct"),
            "explanation": frozen.get("explanation", ""),
            "explanation_kinyarwanda": frozen.get("explanation_kinyarwanda", ""),
            "explanation_french": frozen.get("explanation_french", ""),
        })

    exam_title = "Official Rwanda Traffic Theory Examination"
    exam_id = session.get("exam_id")
    if exam_id:
        exam = ExamService.get_exam(str(exam_id))
        if exam:
            exam_title = exam.get("title", exam_title)

    return {
        "id": session.get("id"),
        "exam_id": exam_id,
        "exam_title": exam_title,
        "track": session.get("track", "STUDENT"),
        "status": session.get("status"),
        "started_at": session.get("started_at"),
        "submitted_at": session.get("submitted_at"),
        "duration_minutes": session.get("duration_minutes", 20),
        "score": session.get("score"),
        "total_questions": len(formatted_questions),
        "passing_score": session.get("passing_score", 12),
        "passed": session.get("passed"),
        "violation_count": session.get("violation_count", 0),
        "questions": formatted_questions,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Student Scheduled Examination Endpoints
# ──────────────────────────────────────────────────────────────────────────────

class StudentExamListView(SuccessResponseMixin, APIView):
    """Lists official scheduled exams available to the authenticated student."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        exams = ExamEngineService.list_student_available_exams(request.user)
        return self.success_response(
            data=exams,
            message="Available examinations retrieved successfully.",
        )


class StudentExamStartView(SuccessResponseMixin, APIView):
    """
    Initiates or resumes a student's scheduled examination attempt.
    Enforces exactly 1 attempt per window policy.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, exam_id):
        serializer = StartStudentExamSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        exam = ExamService.get_exam(str(exam_id))
        if not exam:
            return self.error_response(
                code="EXAM_NOT_FOUND",
                message="Scheduled examination window not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        student_id = str(request.user.id)
        existing_attempt = ExamEngineService.get_student_attempt_for_exam(student_id, str(exam_id))

        if existing_attempt:
            # Check if active and not expired
            if existing_attempt.get("status") == "ACTIVE":
                now = timezone.now()
                expires_at_str = existing_attempt.get("expires_at", "")
                if expires_at_str:
                    try:
                        exp = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
                        if now <= exp:
                            # Resume active session
                            formatted = _format_active_session(existing_attempt)
                            return self.success_response(
                                data=formatted,
                                message="Resumed active examination session.",
                            )
                        else:
                            # Expired -> Auto grade
                            ExamEngineService.grade_session(existing_attempt["id"])
                    except Exception:
                        pass

            # If already completed or expired
            return self.error_response(
                code="ATTEMPT_LIMIT_REACHED",
                message="You have already completed your 1 permitted attempt for this examination window.",
                errors={"attempt_id": existing_attempt.get("id"), "status": existing_attempt.get("status")},
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # Check window dates
        now = timezone.now()
        open_date_str = exam.get("open_date")
        closing_date_str = exam.get("closing_date")

        if open_date_str:
            try:
                open_dt = datetime.fromisoformat(open_date_str.replace("Z", "+00:00"))
                if now < open_dt:
                    return self.error_response(
                        code="EXAM_NOT_OPEN",
                        message="This examination window has not opened yet.",
                        status_code=status.HTTP_400_BAD_REQUEST,
                    )
            except Exception:
                pass

        if closing_date_str:
            try:
                close_dt = datetime.fromisoformat(closing_date_str.replace("Z", "+00:00"))
                if now > close_dt:
                    return self.error_response(
                        code="EXAM_CLOSED",
                        message="This examination window is closed.",
                        status_code=status.HTTP_400_BAD_REQUEST,
                    )
            except Exception:
                pass

        # Create new 20-min session with 20 randomly pulled domain questions
        session = ExamEngineService.start_exam_session(
            student=request.user,
            exam_id=str(exam_id),
            track="STUDENT",
            duration_minutes=20,
        )

        # Record pre-flight selfie and diagnostics
        selfie = data.get("selfie_image")
        checks = data.get("preflight_checks")
        if selfie or checks:
            ExamEngineService.record_preflight_identity(
                session_id=session["id"],
                selfie_image=selfie,
                preflight_checks=checks,
            )

        formatted = _format_active_session(session)
        return self.success_response(
            data=formatted,
            message="Official examination started. Timer has begun (20 minutes).",
            status_code=status.HTTP_201_CREATED,
        )


# ──────────────────────────────────────────────────────────────────────────────
# Candidate Session Execution Endpoints (Student, Guest & Public)
# ──────────────────────────────────────────────────────────────────────────────

class CandidateSessionDetailView(SuccessResponseMixin, APIView):
    """Fetches candidate session state (active runner or graded results)."""
    permission_classes = [AllowAny]

    def get(self, request, session_id):
        session = ExamEngineService.get_session(str(session_id))
        if not session:
            return self.error_response(
                code="SESSION_NOT_FOUND",
                message="Examination session not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        # Check if active session expired
        if session.get("status") == "ACTIVE":
            now = timezone.now()
            expires_at_str = session.get("expires_at", "")
            if expires_at_str:
                try:
                    exp = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
                    if now > exp:
                        ExamEngineService.grade_session(str(session_id))
                        session = ExamEngineService.get_session(str(session_id))
                except Exception:
                    pass

        if session.get("status") in ("BOARD_REVIEW", "TRAINING_REVIEW", "SYSTEM_REVIEW", "APPROVED", "PUBLISHED", "REJECTED"):
            formatted = _format_results_session(session)
        else:
            formatted = _format_active_session(session)

        return self.success_response(
            data=formatted,
            message="Examination session retrieved.",
        )


class CandidateSessionAnswerView(SuccessResponseMixin, APIView):
    """Records an answer during an active exam attempt."""
    permission_classes = [AllowAny]

    def post(self, request, session_id):
        serializer = RecordAnswerSerializer(data=request.data)
        if not serializer.is_valid():
            return self.error_response(
                code="VALIDATION_ERROR",
                message="Invalid answer submission.",
                errors=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        seq = serializer.validated_data["sequence_number"]
        opt = serializer.validated_data["selected_option"]

        try:
            target_q = ExamEngineService.record_answer(
                session_id=str(session_id),
                sequence_number=seq,
                selected_option=opt,
            )
            return self.success_response(
                data={
                    "sequence_number": target_q.get("sequence_number"),
                    "selected_option": target_q.get("selected_option"),
                    "answered_at": target_q.get("answered_at"),
                },
                message=f"Answer recorded for question #{seq}.",
            )
        except ValueError as err:
            return self.error_response(
                code="ANSWER_ERROR",
                message=str(err),
                status_code=status.HTTP_400_BAD_REQUEST,
            )


class CandidateSessionProctorEventView(SuccessResponseMixin, APIView):
    """Logs proctoring telemetry (tab switches, webcam snapshots, mic anomalies)."""
    permission_classes = [AllowAny]

    def post(self, request, session_id):
        serializer = ProctorEventInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            event = ExamEngineService.record_proctoring_event(
                session_id=str(session_id),
                event_type=data["event_type"],
                snapshot_image=data.get("snapshot_image", ""),
                metadata=data.get("metadata", {}),
                is_violation=data.get("is_violation", True),
            )
            return self.success_response(
                data=event,
                message="Proctoring event logged.",
                status_code=status.HTTP_201_CREATED,
            )
        except ValueError as err:
            return self.error_response(
                code="PROCTOR_ERROR",
                message=str(err),
                status_code=status.HTTP_400_BAD_REQUEST,
            )


class CandidateSessionSubmitView(SuccessResponseMixin, APIView):
    """Submits the exam, calculates auto-grade, and transitions status."""
    permission_classes = [AllowAny]

    def post(self, request, session_id):
        try:
            session = ExamEngineService.grade_session(str(session_id))
            formatted = _format_results_session(session)
            return self.success_response(
                data=formatted,
                message="Examination successfully submitted and graded.",
            )
        except ValueError as err:
            return self.error_response(
                code="SUBMISSION_ERROR",
                message=str(err),
                status_code=status.HTTP_400_BAD_REQUEST,
            )


class CandidateSessionResultsView(SuccessResponseMixin, APIView):
    """Post-submission answer and theory explanation review."""
    permission_classes = [AllowAny]

    def get(self, request, session_id):
        session = ExamEngineService.get_session(str(session_id))
        if not session:
            return self.error_response(
                code="SESSION_NOT_FOUND",
                message="Examination session not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        formatted = _format_results_session(session)
        return self.success_response(
            data=formatted,
            message="Examination results and answer review retrieved.",
        )


# ──────────────────────────────────────────────────────────────────────────────
# Guest & Public Paid Examination Endpoints
# ──────────────────────────────────────────────────────────────────────────────

class PublicExamPackagesView(SuccessResponseMixin, APIView):
    """Lists available practice exam packages and pricing."""
    permission_classes = [AllowAny]

    def get(self, request):
        packages = ExamCreditService.list_packages()
        return self.success_response(
            data=packages,
            message="Practice exam packages retrieved.",
        )


class PublicExamCreditsView(SuccessResponseMixin, APIView):
    """Retrieves practice exam credits for a guest user or phone number."""
    permission_classes = [AllowAny]

    def get(self, request):
        phone = request.query_params.get("phone_number")
        if not phone and request.user and request.user.is_authenticated:
            phone = getattr(request.user, "phone_number", None) or str(request.user.id)

        if not phone:
            return self.error_response(
                code="PHONE_REQUIRED",
                message="Phone number is required to look up exam credits.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        balance = ExamCreditService.get_credit_balance(phone)
        return self.success_response(
            data=balance,
            message="Exam credit balance retrieved.",
        )


class PublicExamBuyView(SuccessResponseMixin, APIView):
    """Purchases practice exam credits via MoMo."""
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = BuyExamPackageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        user = request.user if request.user and request.user.is_authenticated else None
        phone = data.get("phone_number")
        if not phone and user:
            phone = getattr(user, "phone_number", None)

        if not phone:
            return self.error_response(
                code="PHONE_REQUIRED",
                message="Phone number is required to receive exam credits.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = ExamCreditService.purchase_package(
                phone_number=phone,
                paying_number=data["paying_number"],
                package_key=data["package_key"],
                user=user,
            )
            return self.success_response(
                data=result,
                message=result["message"],
                status_code=status.HTTP_201_CREATED,
            )
        except ValueError as err:
            return self.error_response(
                code="PURCHASE_FAILED",
                message=str(err),
                status_code=status.HTTP_400_BAD_REQUEST,
            )


class PublicExamStartView(SuccessResponseMixin, APIView):
    """
    Consumes 1 exam credit and initiates a 20-min practice exam session
    for Guest / Public candidates (auto-graded immediately upon submission).
    """
    permission_classes = [AllowAny]

    def post(self, request):
        user = request.user if request.user and request.user.is_authenticated else None
        phone = request.data.get("phone_number")
        if not phone and user:
            phone = getattr(user, "phone_number", None) or str(user.id)

        if not phone:
            return self.error_response(
                code="PHONE_REQUIRED",
                message="Phone number is required to start a practice exam.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # Attempt to consume 1 credit
        consumed = ExamCreditService.consume_credit(phone)
        if not consumed:
            # If guest user has an account, check by user ID as well
            if user:
                consumed = ExamCreditService.consume_credit(str(user.id))

        if not consumed:
            return self.error_response(
                code="INSUFFICIENT_CREDITS",
                message="You have no remaining exam credits. Please purchase an exam package with MoMo.",
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
            )

        track = "GUEST" if user else "PUBLIC"
        student_obj = user or phone
        session = ExamEngineService.start_exam_session(
            student=student_obj,
            exam_id=None,
            track=track,
            duration_minutes=20,
        )

        formatted = _format_active_session(session)
        return self.success_response(
            data=formatted,
            message="Practice exam started. Timer has begun (20 minutes). Fullscreen recommended.",
            status_code=status.HTTP_201_CREATED,
        )
