"""
apps/examinations/views/session_views.py
========================================
Administrative examination sessions, review pipeline, and publishing endpoints.
Fully resilient: works with PostgreSQL or file-backed storage if database is offline.
"""

import logging
from typing import Any, Dict
from django.db.models import Q
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.core.mixins import SuccessResponseMixin
from apps.core.pagination import StandardResultsPagination
from apps.core.permissions import IsAdminLevel, IsSystemAdmin
from apps.examinations.models import ExamSession, ExamSessionStatus
from apps.examinations.serializers import (
    AdminExamPublishSerializer,
    AdminExamSessionDetailSerializer,
    AdminExamSessionListSerializer,
    AdminExamStageActionSerializer,
)
from apps.examinations.services import ExamEngineService, ExamWorkflowService

logger = logging.getLogger(__name__)


def _format_admin_session_payload(s: Dict[str, Any], include_details: bool = False) -> Dict[str, Any]:
    st = s.get("status", "BOARD_REVIEW")
    rev_info = {"stage": st, "reviewer_name": "", "label": st}
    if st == "BOARD_REVIEW":
        rev_info = {
            "stage": "BOARD_REVIEW",
            "reviewer_name": s.get("board_reviewer_name") or "Awaiting Board Reviewer",
            "label": "Board Reviewer",
        }
    elif st == "TRAINING_REVIEW":
        rev_info = {
            "stage": "TRAINING_REVIEW",
            "reviewer_name": s.get("training_admin_name") or "Awaiting Training Admin",
            "label": "Training Admin",
        }
    elif st == "SYSTEM_REVIEW":
        rev_info = {
            "stage": "SYSTEM_REVIEW",
            "reviewer_name": "System Administrator",
            "label": "Ready for Approval",
        }
    elif st == "APPROVED":
        rev_info = {
            "stage": "APPROVED",
            "reviewer_name": "Certified",
            "label": "Approved — Ready to Publish",
        }
    elif st == "PUBLISHED":
        rev_info = {
            "stage": "PUBLISHED",
            "reviewer_name": "Official",
            "label": "Published",
        }

    data = {
        "id": s.get("id"),
        "student_name": s.get("student_name") or "Candidate",
        "student_phone": s.get("student_phone") or s.get("phone_number") or "",
        "student_role": "STUDENT" if (s.get("track") or "STUDENT").upper() == "STUDENT" else "GUEST",
        "student_code": s.get("student_code") or s.get("student_id") or "CAND-001",
        "cohort_name": s.get("cohort_name") or "Cohort 1 (Kigali Alpha)",
        "cohort_id": s.get("cohort_id"),
        "track": (s.get("track") or "STUDENT").upper(),
        "status": st,
        "score": s.get("score"),
        "total_questions": s.get("total_questions", 20),
        "passed": s.get("passed"),
        "violation_count": s.get("violation_count", 0),
        "submitted_at": s.get("submitted_at"),
        "started_at": s.get("started_at"),
        "approved_at": s.get("approved_at"),
        "published_at": s.get("published_at"),
        "is_published": s.get("is_published", False),
        "has_certificate": s.get("has_certificate", False),
        "certificate_number": s.get("certificate_number", ""),
        "current_reviewer_info": rev_info,
        "can_publish": (st == "APPROVED"),
        "created_at": s.get("created_at"),
    }

    if include_details:
        session_questions = []
        for q in s.get("session_questions", []):
            f = q.get("frozen_data", {})
            session_questions.append({
                "id": str(f.get("id", q.get("sequence_number"))),
                "sequence_number": q.get("sequence_number"),
                "selected_option": q.get("selected_option", ""),
                "correct_option": (f.get("correct_option") or "A").strip().upper(),
                "is_correct": q.get("is_correct"),
                "answered_at": q.get("answered_at"),
                "domain": f.get("domain", "GENERAL"),
                "question_text": f.get("question_text", ""),
                "question_text_kinyarwanda": f.get("question_text_kinyarwanda", ""),
                "option_a": f.get("option_a", ""),
                "option_b": f.get("option_b", ""),
                "option_c": f.get("option_c", ""),
                "option_d": f.get("option_d", ""),
                "option_a_kinyarwanda": f.get("option_a_kinyarwanda", ""),
                "option_b_kinyarwanda": f.get("option_b_kinyarwanda", ""),
                "option_c_kinyarwanda": f.get("option_c_kinyarwanda", ""),
                "option_d_kinyarwanda": f.get("option_d_kinyarwanda", ""),
                "explanation": f.get("explanation", ""),
                "image": f.get("image"),
            })

        proctoring_events = s.get("proctoring_events", [])
        data.update({
            "session_questions": session_questions,
            "proctoring_events": proctoring_events,
            "identity_image": s.get("identity_image"),
            "preflight_checks": s.get("preflight_checks", {}),
            "board_reviewed_at": s.get("board_reviewed_at"),
            "board_decision": s.get("board_decision"),
            "board_notes": s.get("board_notes", ""),
            "board_reviewer_name": s.get("board_reviewer_name"),
            "training_reviewed_at": s.get("training_reviewed_at"),
            "training_decision": s.get("training_decision"),
            "training_notes": s.get("training_notes", ""),
            "training_admin_name": s.get("training_admin_name"),
            "approved_by_name": s.get("approved_by_name"),
            "approval_notes": s.get("approval_notes", ""),
            "published_by_name": s.get("published_by_name"),
        })

    return data


class AdminExamSessionListView(SuccessResponseMixin, APIView):
    """
    Lists exam sessions for administrator oversight.
    Supports filtering by cohort_id, status/stage, track, and candidate search query.
    """
    permission_classes = [IsAuthenticated, IsAdminLevel]

    def get(self, request):
        cohort_id = request.query_params.get("cohort_id")
        stage = request.query_params.get("stage") or request.query_params.get("status")
        track = request.query_params.get("track")
        search = request.query_params.get("search")

        # Try database first
        try:
            qs = ExamSession.objects.select_related("student", "cohort", "certificate").order_by("-created_at")
            if cohort_id:
                qs = qs.filter(cohort_id=cohort_id)
            if stage and stage.upper() != "ALL":
                qs = qs.filter(status=stage.upper())
            if track and track.upper() != "ALL":
                qs = qs.filter(track=track.upper())
            if search:
                s_clean = search.strip()
                qs = qs.filter(
                    Q(student__phone_number__icontains=s_clean)
                    | Q(student__first_name__icontains=s_clean)
                    | Q(student__last_name__icontains=s_clean)
                    | Q(student__student_id__icontains=s_clean)
                )

            paginator = StandardResultsPagination()
            page = paginator.paginate_queryset(qs, request)
            if page is not None:
                serializer = AdminExamSessionListSerializer(page, many=True)
                return paginator.get_paginated_response(serializer.data)

            serializer = AdminExamSessionListSerializer(qs, many=True)
            return self.success_response(data={"count": qs.count(), "results": serializer.data})
        except Exception as db_err:
            logger.debug("Database session list fallback to file: %s", db_err)

        # File fallback
        sessions = ExamEngineService.list_all_sessions(
            cohort_id=cohort_id,
            stage=stage,
            track=track,
            search=search,
        )
        formatted_list = [_format_admin_session_payload(s, include_details=False) for s in sessions]
        return self.success_response(
            data={"count": len(formatted_list), "results": formatted_list},
            message="Exam sessions retrieved successfully.",
        )


class AdminExamSessionDetailView(SuccessResponseMixin, APIView):
    """
    Detailed inspection of a single exam session:
    Includes all 20 questions with student options vs correct keys,
    proctoring events, and stage review audit notes.
    """
    permission_classes = [IsAuthenticated, IsAdminLevel]

    def get(self, request, pk):
        session_id = str(pk)
        try:
            db_session = ExamSession.objects.select_related(
                "student", "cohort", "certificate", "board_reviewer", "training_admin", "approved_by", "published_by"
            ).prefetch_related("session_questions__question", "proctoring_events").get(id=session_id)
            serializer = AdminExamSessionDetailSerializer(db_session)
            return self.success_response(data=serializer.data, message="Session details retrieved.")
        except Exception as db_err:
            logger.debug("Database session detail fallback to file: %s", db_err)

        # Fallback
        session = ExamEngineService.get_session(session_id)
        if not session:
            return self.error_response(
                code="NOT_FOUND",
                message="Exam session not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        payload = _format_admin_session_payload(session, include_details=True)
        return self.success_response(data=payload, message="Session details retrieved.")


class AdminExamStageActionView(SuccessResponseMixin, APIView):
    """
    Handles stage progression actions.
    Enforces strict sequential governance:
    - Board Reviewer reviews and advances to TRAINING_REVIEW.
    - Training Admin reviews and advances to SYSTEM_REVIEW.
    - System Admin approval (SYSTEM_APPROVE) is strictly locked until Training Admin review is complete.
    """
    permission_classes = [IsAuthenticated, IsAdminLevel]

    def post(self, request, session_id, *args, **kwargs):
        serializer = AdminExamStageActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        action = serializer.validated_data["action"]
        decision = serializer.validated_data.get("decision", "APPROVE")
        notes = serializer.validated_data.get("notes", "")

        user_role = getattr(request.user, "role", "")
        is_superuser = getattr(request.user, "is_superuser", False)

        if action == "BOARD_DECISION":
            if not (user_role == "BOARD_REVIEWER" or is_superuser):
                return self.error_response(
                    code="PERMISSION_DENIED",
                    message="Only Board Reviewers can perform Stage 1 Board Reviews.",
                    status_code=status.HTTP_403_FORBIDDEN,
                )
            if decision.upper() == "APPROVE" and not (notes and notes.strip()):
                return self.error_response(
                    code="COMMENT_REQUIRED",
                    message="A review comment is required when approving Stage 1.",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
            msg = f"Board review recorded: {decision}."
        elif action == "TRAINING_DECISION":
            if not (user_role == "TRAINING_ADMIN" or is_superuser):
                return self.error_response(
                    code="PERMISSION_DENIED",
                    message="Only Training Administrators can perform Stage 2 Pedagogical Audits.",
                    status_code=status.HTTP_403_FORBIDDEN,
                )
            if decision.upper() == "APPROVE" and not (notes and notes.strip()):
                return self.error_response(
                    code="COMMENT_REQUIRED",
                    message="An audit comment is required when approving Stage 2.",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
            msg = f"Training Administrator audit recorded: {decision}."
        elif action == "SYSTEM_APPROVE":
            if not (user_role == "SYSTEM_ADMIN" or is_superuser):
                return self.error_response(
                    code="PERMISSION_DENIED",
                    message="Only System Administrators can execute final approval and issue certificates.",
                    status_code=status.HTTP_403_FORBIDDEN,
                )
            msg = "System Admin approved exam session. Certificate auto-generated successfully."
        elif action == "REJECT":
            msg = "Exam session marked as Rejected."
        else:
            return self.error_response(
                code="INVALID_ACTION",
                message=f"Unknown review action '{action}'.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # Try database workflow first
        try:
            if action == "BOARD_DECISION":
                db_session = ExamWorkflowService.board_review_decision(
                    session_id=str(session_id),
                    reviewer=request.user,
                    decision=decision,
                    notes=notes,
                )
            elif action == "TRAINING_DECISION":
                db_session = ExamWorkflowService.training_admin_review_decision(
                    session_id=str(session_id),
                    reviewer=request.user,
                    decision=decision,
                    notes=notes,
                )
            elif action == "SYSTEM_APPROVE":
                db_session = ExamWorkflowService.system_admin_approve(
                    session_id=str(session_id),
                    system_admin=request.user,
                    notes=notes,
                )
            elif action == "REJECT":
                db_session = ExamSession.objects.get(id=session_id)
                db_session.status = ExamSessionStatus.REJECTED
                db_session.approval_notes = notes
                db_session.save(update_fields=["status", "approval_notes", "updated_at"])

            return self.success_response(
                data=AdminExamSessionDetailSerializer(db_session).data,
                message=msg,
            )
        except Exception as db_err:
            logger.debug("Database workflow action fallback to engine service: %s", db_err)

        # File fallback
        try:
            updated_session = ExamEngineService.update_session_stage_action(
                session_id=str(session_id),
                action=action,
                decision=decision,
                notes=notes,
                reviewer_user=request.user,
            )
            payload = _format_admin_session_payload(updated_session, include_details=True)
            return self.success_response(data=payload, message=msg)
        except ValueError as val_err:
            return self.error_response(
                code="GOVERNANCE_LOCK",
                message=str(val_err),
                status_code=status.HTTP_400_BAD_REQUEST,
            )


class AdminExamPublishView(SuccessResponseMixin, APIView):
    """
    Flexible publishing endpoint:
    - Single Exam: payload has 'session_id'
    - Multi-select: payload has 'session_ids'
    - Whole Cohort: payload has 'cohort_id'
    Requires System Admin privileges.
    """
    permission_classes = [IsAuthenticated, IsSystemAdmin]

    def post(self, request, *args, **kwargs):
        serializer = AdminExamPublishSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        session_id = data.get("session_id")
        session_ids = data.get("session_ids")
        cohort_id = data.get("cohort_id")

        # Try database first
        try:
            if cohort_id:
                result = ExamWorkflowService.publish_cohort(str(cohort_id), request.user)
                return self.success_response(
                    data=result,
                    message=f"Published all {result['published_count']} approved exam sessions for cohort.",
                )
            elif session_ids and len(session_ids) > 0:
                result = ExamWorkflowService.publish_batch([str(sid) for sid in session_ids], request.user)
                return self.success_response(
                    data=result,
                    message=f"Batch published {result['published_count']} approved exam sessions.",
                )
            elif session_id:
                session = ExamWorkflowService.publish_exam(str(session_id), request.user)
                return self.success_response(
                    data=AdminExamSessionDetailSerializer(session).data,
                    message="Exam session published successfully.",
                )
        except Exception as db_err:
            logger.debug("Database publish fallback to engine service: %s", db_err)

        # File fallback
        try:
            if session_id:
                updated = ExamEngineService.publish_session_fallback(str(session_id), request.user)
                payload = _format_admin_session_payload(updated, include_details=True)
                return self.success_response(data=payload, message="Exam session published successfully.")
            elif session_ids:
                count = 0
                for sid in session_ids:
                    ExamEngineService.publish_session_fallback(str(sid), request.user)
                    count += 1
                return self.success_response(
                    data={"published_count": count},
                    message=f"Batch published {count} exam sessions.",
                )
            else:
                return self.error_response(
                    code="INVALID_PAYLOAD",
                    message="Must provide either session_id or session_ids.",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
        except ValueError as err:
            return self.error_response(
                code="PUBLISH_ERROR",
                message=str(err),
                status_code=status.HTTP_400_BAD_REQUEST,
            )
