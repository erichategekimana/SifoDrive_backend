"""
apps/examinations/serializers.py
================================
Serializers for Examination Hub, review pipeline, certificates, and question bank.
"""

from rest_framework import serializers

from apps.examinations.models import (
    Certificate,
    CertificateTemplate,
    ExamSession,
    ExamSessionStatus,
    ProctoringEvent,
    SessionQuestion,
)
from apps.lms.models import QuizQuestion


class CertificateTemplateSerializer(serializers.ModelSerializer):
    """Administrative serializer for customizing certificate templates."""

    class Meta:
        model = CertificateTemplate
        fields = [
            "id",
            "template_type",
            "header_subtitle",
            "title",
            "conferral_text",
            "course_name",
            "declaration_text",
            "confirmation_notes",
            "logo_url",
            "training_admin_name",
            "training_admin_title",
            "training_admin_signature",
            "director_name",
            "director_title",
            "director_signature",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class CertificateSerializer(serializers.ModelSerializer):
    """Serializer for issued official certificates."""

    class Meta:
        model = Certificate
        fields = [
            "id",
            "certificate_number",
            "student_name",
            "student_code",
            "track_type",
            "enterprise_name",
            "started_at",
            "completed_at",
            "score",
            "total_questions",
            "passing_score",
            "passed",
            "issue_date",
            "verification_hash",
            "verification_url",
            "template_snapshot",
            "is_valid",
            "created_at",
        ]
        read_only_fields = fields


class SessionQuestionDetailSerializer(serializers.ModelSerializer):
    """Detailed review of a question in an exam session."""

    question_text = serializers.CharField(source="question.question_text", read_only=True)
    question_text_kinyarwanda = serializers.CharField(source="question.question_text_kinyarwanda", read_only=True)
    option_a = serializers.CharField(source="question.option_a", read_only=True)
    option_b = serializers.CharField(source="question.option_b", read_only=True)
    option_c = serializers.CharField(source="question.option_c", read_only=True)
    option_d = serializers.CharField(source="question.option_d", read_only=True)
    option_a_kinyarwanda = serializers.CharField(source="question.option_a_kinyarwanda", read_only=True)
    option_b_kinyarwanda = serializers.CharField(source="question.option_b_kinyarwanda", read_only=True)
    option_c_kinyarwanda = serializers.CharField(source="question.option_c_kinyarwanda", read_only=True)
    option_d_kinyarwanda = serializers.CharField(source="question.option_d_kinyarwanda", read_only=True)
    correct_option = serializers.CharField(source="question.correct_option", read_only=True)
    explanation = serializers.CharField(source="question.explanation", read_only=True)
    image = serializers.ImageField(source="question.image", read_only=True)
    domain = serializers.CharField(source="question.domain", read_only=True)

    class Meta:
        model = SessionQuestion
        fields = [
            "id",
            "sequence_number",
            "selected_option",
            "correct_option",
            "is_correct",
            "answered_at",
            "domain",
            "question_text",
            "question_text_kinyarwanda",
            "option_a",
            "option_b",
            "option_c",
            "option_d",
            "option_a_kinyarwanda",
            "option_b_kinyarwanda",
            "option_c_kinyarwanda",
            "option_d_kinyarwanda",
            "explanation",
            "image",
        ]


class ProctoringEventSerializer(serializers.ModelSerializer):
    """Records proctoring telemetry snapshots and violation logs."""

    class Meta:
        model = ProctoringEvent
        fields = [
            "id",
            "event_type",
            "snapshot_image",
            "metadata",
            "is_violation",
            "created_at",
        ]


class AdminExamSessionListSerializer(serializers.ModelSerializer):
    """Summary row for the administrative examinations table."""

    student_name = serializers.SerializerMethodField()
    student_phone = serializers.CharField(source="student.phone_number", read_only=True)
    student_role = serializers.CharField(source="student.role", read_only=True)
    student_code = serializers.SerializerMethodField()
    cohort_name = serializers.CharField(source="cohort.name", read_only=True, default=None)
    cohort_id = serializers.UUIDField(source="cohort.id", read_only=True, default=None)
    has_certificate = serializers.SerializerMethodField()
    certificate_number = serializers.SerializerMethodField()
    current_reviewer_info = serializers.SerializerMethodField()

    class Meta:
        model = ExamSession
        fields = [
            "id",
            "student_name",
            "student_phone",
            "student_role",
            "student_code",
            "cohort_name",
            "cohort_id",
            "track",
            "status",
            "score",
            "total_questions",
            "passed",
            "violation_count",
            "submitted_at",
            "started_at",
            "approved_at",
            "published_at",
            "is_published",
            "has_certificate",
            "certificate_number",
            "current_reviewer_info",
            "created_at",
        ]

    def get_student_name(self, obj: ExamSession) -> str:
        return obj.student.get_full_name() or obj.student.phone_number

    def get_student_code(self, obj: ExamSession) -> str:
        return getattr(obj.student, "student_id", "") or obj.student.phone_number

    def get_has_certificate(self, obj: ExamSession) -> bool:
        return hasattr(obj, "certificate") and obj.certificate is not None

    def get_certificate_number(self, obj: ExamSession) -> str:
        if hasattr(obj, "certificate") and obj.certificate:
            return obj.certificate.certificate_number
        return ""

    def get_current_reviewer_info(self, obj: ExamSession) -> dict:
        if obj.status == ExamSessionStatus.BOARD_REVIEW:
            rev_name = obj.board_reviewer.get_full_name() if obj.board_reviewer else "Awaiting Board Reviewer"
            return {"stage": "BOARD_REVIEW", "reviewer_name": rev_name, "label": "Board Reviewer"}
        elif obj.status == ExamSessionStatus.TRAINING_REVIEW:
            rev_name = obj.training_admin.get_full_name() if obj.training_admin else "Awaiting Training Admin"
            return {"stage": "TRAINING_REVIEW", "reviewer_name": rev_name, "label": "Training Admin"}
        elif obj.status == ExamSessionStatus.SYSTEM_REVIEW:
            return {"stage": "SYSTEM_REVIEW", "reviewer_name": "System Administrator", "label": "Ready for Approval"}
        elif obj.status == ExamSessionStatus.APPROVED:
            return {"stage": "APPROVED", "reviewer_name": "Certified", "label": "Approved — Ready to Publish"}
        elif obj.status == ExamSessionStatus.PUBLISHED:
            return {"stage": "PUBLISHED", "reviewer_name": "Official", "label": "Published"}
        return {"stage": obj.status, "reviewer_name": "", "label": obj.get_status_display()}


class AdminExamSessionDetailSerializer(AdminExamSessionListSerializer):
    """Comprehensive inspection view including questions, snapshots, and stage notes."""

    session_questions = SessionQuestionDetailSerializer(many=True, read_only=True)
    proctoring_events = ProctoringEventSerializer(many=True, read_only=True)
    certificate = CertificateSerializer(read_only=True)

    board_reviewer_name = serializers.CharField(source="board_reviewer.get_full_name", read_only=True, default=None)
    training_admin_name = serializers.CharField(source="training_admin.get_full_name", read_only=True, default=None)
    approved_by_name = serializers.CharField(source="approved_by.get_full_name", read_only=True, default=None)
    published_by_name = serializers.CharField(source="published_by.get_full_name", read_only=True, default=None)

    class Meta(AdminExamSessionListSerializer.Meta):
        fields = AdminExamSessionListSerializer.Meta.fields + [
            "session_questions",
            "proctoring_events",
            "certificate",
            "board_reviewed_at",
            "board_decision",
            "board_notes",
            "board_reviewer_name",
            "training_reviewed_at",
            "training_decision",
            "training_notes",
            "training_admin_name",
            "approved_by_name",
            "approval_notes",
            "published_by_name",
        ]


class AdminExamStageActionSerializer(serializers.Serializer):
    """Payload for advancing review stage, certifying, or rejecting."""

    action = serializers.ChoiceField(choices=["BOARD_DECISION", "TRAINING_DECISION", "SYSTEM_APPROVE", "REJECT"])
    decision = serializers.ChoiceField(choices=["APPROVE", "REJECT"], default="APPROVE")
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class AdminExamPublishSerializer(serializers.Serializer):
    """Payload for publishing exam results (single, multi-select, or whole cohort)."""

    session_id = serializers.UUIDField(required=False, allow_null=True)
    session_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        allow_empty=True,
    )
    cohort_id = serializers.UUIDField(required=False, allow_null=True)


class AdminQuizQuestionSerializer(serializers.ModelSerializer):
    """CRUD Serializer for Quiz Questions in LMS / Question Bank Studio."""

    class Meta:
        model = QuizQuestion
        fields = [
            "id",
            "question_number",
            "domain",
            "difficulty",
            "question_text",
            "question_text_kinyarwanda",
            "option_a",
            "option_b",
            "option_c",
            "option_d",
            "option_a_kinyarwanda",
            "option_b_kinyarwanda",
            "option_c_kinyarwanda",
            "option_d_kinyarwanda",
            "option_a_image",
            "option_b_image",
            "option_c_image",
            "option_d_image",
            "correct_option",
            "explanation",
            "explanation_kinyarwanda",
            "image",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

