"""
apps/examinations/views.py
==========================
DRF API views for Examination Hub: multi-stage review pipeline, certificate management,
flexible publishing (single, multi, cohort), public QR verification, and question bank editor.
"""

import logging
from django.db.models import Q
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.mixins import SuccessResponseMixin
from apps.core.pagination import StandardResultsPagination
from apps.core.permissions import IsAdminLevel, IsSystemAdmin
from apps.examinations.models import (
    Certificate,
    CertificateTemplate,
    ExamSession,
    ExamSessionStatus,
)
from apps.examinations.serializers import (
    AdminExamPublishSerializer,
    AdminExamStageActionSerializer,
    AdminExamSessionDetailSerializer,
    AdminExamSessionListSerializer,
    AdminQuizQuestionSerializer,
    CertificateSerializer,
    CertificateTemplateSerializer,
)
from apps.examinations.services import CertificateService, ExamWorkflowService
from apps.lms.models import QuizQuestion

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. Examination Sessions & Multi-Tier Review Pipeline Views
# ---------------------------------------------------------------------------

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
            if action == "BOARD_DECISION":
                session = ExamWorkflowService.board_review_decision(
                    session_id=str(session_id),
                    reviewer=request.user,
                    decision=decision,
                    notes=notes,
                )
                msg = f"Board review recorded: {decision}."
            elif action == "TRAINING_DECISION":
                session = ExamWorkflowService.training_admin_review_decision(
                    session_id=str(session_id),
                    reviewer=request.user,
                    decision=decision,
                    notes=notes,
                )
                msg = f"Training Administrator review recorded: {decision}."
            elif action == "SYSTEM_APPROVE":
                # System Admin final approval
                session = ExamWorkflowService.system_admin_approve(
                    session_id=str(session_id),
                    system_admin=request.user,
                    notes=notes,
                )
                msg = "System Admin approved exam session. Certificate auto-generated successfully."
            elif action == "REJECT":
                session = ExamSession.objects.get(id=session_id)
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


# ---------------------------------------------------------------------------
# 2. Certificate Registry & Template Customizer Views
# ---------------------------------------------------------------------------

class AdminCertificateListView(SuccessResponseMixin, generics.ListAPIView):
    """List issued certificates with search and filter."""
    permission_classes = [IsAuthenticated, IsAdminLevel]
    serializer_class = CertificateSerializer
    pagination_class = StandardResultsPagination

    def get_queryset(self):
        qs = Certificate.objects.all().order_by("-created_at")
        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(
                Q(certificate_number__icontains=search)
                | Q(student_name__icontains=search)
                | Q(student_code__icontains=search)
            )
        track = self.request.query_params.get("track_type")
        if track:
            qs = qs.filter(track_type=track.upper())
        return qs


class AdminCertificateDetailView(SuccessResponseMixin, generics.RetrieveAPIView):
    """View details of an individual issued certificate."""
    permission_classes = [IsAuthenticated, IsAdminLevel]
    serializer_class = CertificateSerializer
    queryset = Certificate.objects.all()


class AdminCertificateTemplateListView(SuccessResponseMixin, APIView):
    """
    Lists all 3 certificate templates (Student, Guest, Enterprise).
    Ensures default templates exist before returning.
    """
    permission_classes = [IsAuthenticated, IsAdminLevel]

    def get(self, request, *args, **kwargs):
        CertificateService.ensure_default_templates()
        templates = CertificateTemplate.objects.all().order_by("template_type")
        serializer = CertificateTemplateSerializer(templates, many=True)
        return self.success_response(data=serializer.data, message="Certificate templates retrieved.")


class AdminCertificateTemplateDetailView(SuccessResponseMixin, generics.RetrieveUpdateAPIView):
    """
    Retrieve or update a specific certificate template (Student, Guest, Enterprise).
    Allows updating declaration wording, confirmation notes, logo URL, and digital signatures.
    """
    permission_classes = [IsAuthenticated, IsAdminLevel]
    serializer_class = CertificateTemplateSerializer
    queryset = CertificateTemplate.objects.all()


class PublicCertificateVerifyView(SuccessResponseMixin, APIView):
    """
    Public verification endpoint accessed via QR code scan or verification URL:
    GET /api/v1/examinations/verify/<verification_hash>/
    Allows anyone to verify legitimacy without authentication.
    """
    permission_classes = [AllowAny]

    def get(self, request, hash_or_code, *args, **kwargs):
        cert = Certificate.objects.filter(
            Q(verification_hash=hash_or_code) | Q(certificate_number__iexact=hash_or_code)
        ).first()

        if not cert or not cert.is_valid:
            return self.error_response(
                code="INVALID_CERTIFICATE",
                message="Certificate not found or has been revoked.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        return self.success_response(
            data={
                "is_valid": cert.is_valid,
                "certificate_number": cert.certificate_number,
                "student_name": cert.student_name,
                "student_code": cert.student_code,
                "track_type": cert.track_type,
                "enterprise_name": cert.enterprise_name,
                "started_at": cert.started_at,
                "completed_at": cert.completed_at,
                "score": cert.score,
                "total_questions": cert.total_questions,
                "passed": cert.passed,
                "issue_date": cert.issue_date,
                "verification_hash": cert.verification_hash,
                "template_snapshot": cert.template_snapshot,
            },
            message="Certificate is authentic and verified in the official Sifo Drive National Registry.",
        )


# ---------------------------------------------------------------------------
# 3. Question Bank Studio (LMS Quiz Questions)
# ---------------------------------------------------------------------------

class AdminQuestionBankListView(SuccessResponseMixin, generics.ListCreateAPIView):
    """
    Search and manage questions in the Question Bank.
    Filter by domain, difficulty, or search by keyword / question number.
    """
    permission_classes = [IsAuthenticated, IsAdminLevel]
    serializer_class = AdminQuizQuestionSerializer
    pagination_class = StandardResultsPagination

    def get_queryset(self):
        qs = QuizQuestion.objects.filter(is_deleted=False).order_by("question_number", "id")

        domain = self.request.query_params.get("domain")
        if domain and domain.upper() != "ALL":
            qs = qs.filter(domain=domain.upper())

        search = self.request.query_params.get("search")
        if search:
            search_clean = search.strip()
            if search_clean.isdigit():
                qs = qs.filter(question_number=int(search_clean))
            else:
                qs = qs.filter(
                    Q(question_text_kinyarwanda__icontains=search_clean)
                    | Q(question_text__icontains=search_clean)
                    | Q(explanation_kinyarwanda__icontains=search_clean)
                    | Q(explanation__icontains=search_clean)
                    | Q(option_a_kinyarwanda__icontains=search_clean)
                    | Q(option_b_kinyarwanda__icontains=search_clean)
                    | Q(option_c_kinyarwanda__icontains=search_clean)
                    | Q(option_d_kinyarwanda__icontains=search_clean)
                )

        return qs


class AdminQuestionBankDetailView(SuccessResponseMixin, generics.RetrieveUpdateDestroyAPIView):
    """
    Inspect, edit, or delete a question in the Question Bank.
    Enables correcting typos in English & Kinyarwanda, editing options,
    changing correct answer, diagrams, and explanations.
    """
    permission_classes = [IsAuthenticated, IsAdminLevel]
    serializer_class = AdminQuizQuestionSerializer
    queryset = QuizQuestion.objects.filter(is_deleted=False)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.is_deleted = True
        instance.is_active = False
        instance.save(update_fields=["is_deleted", "is_active", "updated_at"])
        return self.success_response(data=None, message="Question removed from active pool.")
