import logging
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
from apps.examinations.services import ExamWorkflowService

logger = logging.getLogger(__name__)


class AdminExamSessionListView(SuccessResponseMixin, generics.ListAPIView):
    """
    Lists exam sessions for administrator oversight.
    Supports filtering by:
      - cohort_id: Filter by enrolled cohort (e.g. Cohort 1)
      - status / stage: Filter by lifecycle stage
      - track: 'B2C' or 'B2B'
      - search: Search student name, phone, student code
    """
    permission_classes = [IsAuthenticated, IsAdminLevel]
    serializer_class = AdminExamSessionListSerializer
    pagination_class = StandardResultsPagination

    def get_queryset(self):
        qs = ExamSession.objects.select_related("student", "cohort", "certificate").order_by("-created_at")

        cohort_id = self.request.query_params.get("cohort_id")
        if cohort_id:
            qs = qs.filter(cohort_id=cohort_id)

        stage = self.request.query_params.get("stage") or self.request.query_params.get("status")
        if stage and stage.upper() != "ALL":
            qs = qs.filter(status=stage.upper())

        track = self.request.query_params.get("track")
        if track and track.upper() != "ALL":
            qs = qs.filter(track=track.upper())

        search = self.request.query_params.get("search")
        if search:
            search_clean = search.strip()
            qs = qs.filter(
                Q(student__phone_number__icontains=search_clean)
                | Q(student__first_name__icontains=search_clean)
                | Q(student__last_name__icontains=search_clean)
                | Q(student__student_id__icontains=search_clean)
            )

        return qs


class AdminExamSessionDetailView(SuccessResponseMixin, generics.RetrieveAPIView):
    """
    Detailed inspection of a single exam session:
    Includes all 20 questions with student options vs correct keys,
    proctoring events, and stage review audit notes.
    """
    permission_classes = [IsAuthenticated, IsAdminLevel]
    serializer_class = AdminExamSessionDetailSerializer
    queryset = ExamSession.objects.select_related(
        "student", "cohort", "certificate", "board_reviewer", "training_admin", "approved_by", "published_by"
    ).prefetch_related("session_questions__question", "proctoring_events")


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

        try:
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
                session = ExamWorkflowService.board_review_decision(
                    session_id=str(session_id),
                    reviewer=request.user,
                    decision=decision,
                    notes=notes,
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
                session = ExamWorkflowService.training_admin_review_decision(
                    session_id=str(session_id),
                    reviewer=request.user,
                    decision=decision,
                    notes=notes,
                )
                msg = f"Training Administrator audit recorded: {decision}."
            elif action == "SYSTEM_APPROVE":
                if not (user_role == "SYSTEM_ADMIN" or is_superuser):
                    return self.error_response(
                        code="PERMISSION_DENIED",
                        message="Only System Administrators can execute final approval and issue certificates.",
                        status_code=status.HTTP_403_FORBIDDEN,
                    )
                session = ExamWorkflowService.system_admin_approve(
                    session_id=str(session_id),
                    system_admin=request.user,
                    notes=notes,
                )
                msg = "System Admin approved exam session. Certificate auto-generated successfully."
            elif action == "REJECT":
                session = ExamSession.objects.get(id=session_id)
                if session.status in (ExamSessionStatus.SUBMITTED, ExamSessionStatus.BOARD_REVIEW):
                    if not (user_role == "BOARD_REVIEWER" or is_superuser):
                        return self.error_response(
                            code="PERMISSION_DENIED",
                            message="Only Board Reviewers can reject during Stage 1.",
                            status_code=status.HTTP_403_FORBIDDEN,
                        )
                elif session.status == ExamSessionStatus.TRAINING_REVIEW:
                    if not (user_role == "TRAINING_ADMIN" or is_superuser):
                        return self.error_response(
                            code="PERMISSION_DENIED",
                            message="Only Training Administrators can reject during Stage 2.",
                            status_code=status.HTTP_403_FORBIDDEN,
                        )
                elif session.status == ExamSessionStatus.SYSTEM_REVIEW:
                    if not (user_role == "SYSTEM_ADMIN" or is_superuser):
                        return self.error_response(
                            code="PERMISSION_DENIED",
                            message="Only System Administrators can reject during Stage 3.",
                            status_code=status.HTTP_403_FORBIDDEN,
                        )
                else:
                    return self.error_response(
                        code="INVALID_STATE",
                        message=f"Cannot reject session in '{session.status}' state.",
                        status_code=status.HTTP_400_BAD_REQUEST,
                    )
                session.status = ExamSessionStatus.REJECTED
                session.approval_notes = notes
                session.save(update_fields=["status", "approval_notes", "updated_at"])
                msg = "Exam session marked as Rejected."
            else:
                return self.error_response(
                    code="INVALID_ACTION",
                    message=f"Unknown review action '{action}'.",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )

            return self.success_response(
                data=AdminExamSessionDetailSerializer(session).data,
                message=msg,
            )
        except ValueError as val_err:
            return self.error_response(
                code="GOVERNANCE_LOCK",
                message=str(val_err),
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        except ExamSession.DoesNotExist:
            return self.error_response(
                code="NOT_FOUND",
                message="Exam session not found.",
                status_code=status.HTTP_404_NOT_FOUND,
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
        cohort_id = data.get("cohort_id")
        session_ids = data.get("session_ids")
        session_id = data.get("session_id")

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
            else:
                return self.error_response(
                    code="INVALID_PAYLOAD",
                    message="Must provide either session_id, session_ids, or cohort_id.",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
        except ValueError as err:
            return self.error_response(
                code="PUBLISH_ERROR",
                message=str(err),
                status_code=status.HTTP_400_BAD_REQUEST,
            )
