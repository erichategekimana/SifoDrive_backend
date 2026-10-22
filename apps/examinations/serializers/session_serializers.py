from rest_framework import serializers

from apps.examinations.models import (
    ExamSession,
    ExamSessionStatus,
    ProctoringEvent,
    SessionQuestion,
)
from apps.examinations.serializers.certificate_serializers import CertificateSerializer


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


# ══════════════════════════════════════════════════════════════════════════════
# Candidate Facing Serializers (Student, Guest, Public)
# ══════════════════════════════════════════════════════════════════════════════

class CandidateSessionQuestionSerializer(serializers.Serializer):
    """Question item delivered during an ACTIVE examination session (secrets hidden)."""

    sequence_number = serializers.IntegerField()
    selected_option = serializers.CharField(allow_blank=True, default="")
    answered_at = serializers.CharField(allow_null=True, required=False)

    id = serializers.CharField()
    question_number = serializers.IntegerField()
    domain = serializers.CharField()

    question_text = serializers.CharField()
    question_text_kinyarwanda = serializers.CharField(allow_blank=True, default="")
    question_text_french = serializers.CharField(allow_blank=True, default="")

    option_a = serializers.CharField()
    option_b = serializers.CharField()
    option_c = serializers.CharField()
    option_d = serializers.CharField()

    option_a_kinyarwanda = serializers.CharField(allow_blank=True, default="")
    option_b_kinyarwanda = serializers.CharField(allow_blank=True, default="")
    option_c_kinyarwanda = serializers.CharField(allow_blank=True, default="")
    option_d_kinyarwanda = serializers.CharField(allow_blank=True, default="")

    option_a_french = serializers.CharField(allow_blank=True, default="")
    option_b_french = serializers.CharField(allow_blank=True, default="")
    option_c_french = serializers.CharField(allow_blank=True, default="")
    option_d_french = serializers.CharField(allow_blank=True, default="")

    image = serializers.CharField(allow_null=True, required=False)


class CandidateResultQuestionSerializer(CandidateSessionQuestionSerializer):
    """Question item delivered AFTER submission for answer review."""

    correct_option = serializers.CharField()
    is_correct = serializers.BooleanField(allow_null=True)
    explanation = serializers.CharField(allow_blank=True, default="")
    explanation_kinyarwanda = serializers.CharField(allow_blank=True, default="")
    explanation_french = serializers.CharField(allow_blank=True, default="")


class CandidateSessionStateSerializer(serializers.Serializer):
    """Live state of an active candidate examination session."""

    id = serializers.CharField()
    exam_id = serializers.CharField(allow_null=True)
    exam_title = serializers.CharField(default="Official Theory Examination")
    track = serializers.CharField(default="STUDENT")
    status = serializers.CharField()

    started_at = serializers.CharField()
    expires_at = serializers.CharField()
    duration_minutes = serializers.IntegerField(default=20)
    time_remaining_seconds = serializers.IntegerField(default=1200)

    total_questions = serializers.IntegerField(default=20)
    answered_count = serializers.IntegerField(default=0)
    violation_count = serializers.IntegerField(default=0)

    questions = serializers.ListField(child=serializers.DictField())


class CandidateSessionResultSerializer(serializers.Serializer):
    """Final graded results and answer review."""

    id = serializers.CharField()
    exam_id = serializers.CharField(allow_null=True)
    exam_title = serializers.CharField(default="Official Theory Examination")
    track = serializers.CharField(default="STUDENT")
    status = serializers.CharField()

    started_at = serializers.CharField()
    submitted_at = serializers.CharField(allow_null=True)
    duration_minutes = serializers.IntegerField(default=20)

    score = serializers.IntegerField(allow_null=True)
    total_questions = serializers.IntegerField(default=20)
    passing_score = serializers.IntegerField(default=12)
    passed = serializers.BooleanField(allow_null=True)
    violation_count = serializers.IntegerField(default=0)

    questions = serializers.ListField(child=serializers.DictField())


class RecordAnswerSerializer(serializers.Serializer):
    """Payload to record an answer during an active exam."""

    sequence_number = serializers.IntegerField(min_value=1, max_value=20)
    selected_option = serializers.ChoiceField(choices=["A", "B", "C", "D"])


class ProctorEventInputSerializer(serializers.Serializer):
    """Payload to log a proctoring event or violation snapshot."""

    event_type = serializers.CharField(max_length=64)
    snapshot_image = serializers.CharField(required=False, allow_blank=True, default="")
    metadata = serializers.DictField(required=False, default=dict)
    is_violation = serializers.BooleanField(default=True)


class StartStudentExamSerializer(serializers.Serializer):
    """Preflight diagnostic confirmation payload to launch student exam."""

    selfie_image = serializers.CharField(required=False, allow_blank=True, default="")
    preflight_checks = serializers.DictField(required=False, default=dict)


class BuyExamPackageSerializer(serializers.Serializer):
    """Payload to purchase exam credits via MoMo."""

    package_key = serializers.CharField(max_length=32)
    paying_number = serializers.CharField(max_length=32)
    phone_number = serializers.CharField(max_length=32, required=False, allow_blank=True)
    full_name = serializers.CharField(max_length=128, required=False, allow_blank=True)
    exam_count = serializers.IntegerField(required=False, min_value=1, max_value=100)

