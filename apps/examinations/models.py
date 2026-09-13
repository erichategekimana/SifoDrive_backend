"""
apps/examinations/models.py
============================
Exam engine models: ExamSession, SessionQuestion, ProctoringEvent, CertificateTemplate, Certificate.
Supports strictly sequential multi-tier review:
Submitted -> Board Reviewer -> Training Admin -> System Admin Approval -> Published.
"""
from django.db import models
from django.utils.translation import gettext_lazy as _
from apps.core.models import BaseModel


class ExamSessionStatus(models.TextChoices):
    PENDING = "PENDING", _("Pending Pre-flight")
    ACTIVE = "ACTIVE", _("In Progress")
    SUBMITTED = "SUBMITTED", _("Submitted — Awaiting Board Review")
    BOARD_REVIEW = "BOARD_REVIEW", _("Under Board Review")
    TRAINING_REVIEW = "TRAINING_REVIEW", _("Under Training Admin Review")
    SYSTEM_REVIEW = "SYSTEM_REVIEW", _("Awaiting System Admin Approval")
    APPROVED = "APPROVED", _("Approved — Certificate Auto-Generated")
    PUBLISHED = "PUBLISHED", _("Published — Official Results Released")
    FLAGGED = "FLAGGED", _("Flagged — Integrity Violation")
    REJECTED = "REJECTED", _("Rejected")
    EXPIRED = "EXPIRED", _("Expired — Time Limit Exceeded")


class ExamSession(BaseModel):
    """A single exam attempt by a student, guest, or enterprise examinee."""
    TRACKS = [('B2C', 'Personal (Remote)'), ('B2B', 'Enterprise Lab')]

    student = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='exam_sessions')
    cohort = models.ForeignKey(
        'live_classes.Cohort',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='exam_sessions',
        verbose_name=_('Enrolled Cohort'),
    )
    track = models.CharField(_('Track'), max_length=5, choices=TRACKS, default='B2C')
    status = models.CharField(
        _('Status'),
        max_length=25,
        choices=ExamSessionStatus.choices,
        default=ExamSessionStatus.PENDING,
        db_index=True,
    )
    started_at = models.DateTimeField(_('Started At'), null=True, blank=True)
    submitted_at = models.DateTimeField(_('Submitted At'), null=True, blank=True)
    expires_at = models.DateTimeField(_('Expires At'), null=True, blank=True)
    score = models.PositiveSmallIntegerField(_('Score'), null=True, blank=True)
    total_questions = models.PositiveSmallIntegerField(_('Total Questions'), default=20)
    passed = models.BooleanField(_('Passed'), null=True, blank=True)
    device_fingerprint = models.CharField(_('Device Fingerprint'), max_length=200, blank=True)
    violation_count = models.PositiveSmallIntegerField(_('Violation Count'), default=0)

    # ── Review Pipeline Stage Tracking ──────────────────────────────────────────
    # Stage 1: Board Reviewer
    board_reviewer = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='board_reviewed_sessions',
        verbose_name=_('Board Reviewer'),
    )
    board_reviewed_at = models.DateTimeField(_('Board Reviewed At'), null=True, blank=True)
    board_decision = models.CharField(_('Board Decision'), max_length=20, blank=True, default='')
    board_notes = models.TextField(_('Board Review Notes'), blank=True, default='')

    # Stage 2: Training Administrator
    training_admin = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='training_reviewed_sessions',
        verbose_name=_('Training Administrator'),
    )
    training_reviewed_at = models.DateTimeField(_('Training Reviewed At'), null=True, blank=True)
    training_decision = models.CharField(_('Training Decision'), max_length=20, blank=True, default='')
    training_notes = models.TextField(_('Training Review Notes'), blank=True, default='')

    # Stage 3: System Administrator (Final Approval & Certificate Generation)
    approved_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='system_approved_sessions',
        verbose_name=_('Approved By'),
    )
    approved_at = models.DateTimeField(_('Approved At'), null=True, blank=True)
    approval_notes = models.TextField(_('System Approval Notes'), blank=True, default='')

    # Stage 4: Result Publishing
    published_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='published_sessions',
        verbose_name=_('Published By'),
    )
    published_at = models.DateTimeField(_('Published At'), null=True, blank=True)
    is_published = models.BooleanField(_('Is Published'), default=False, db_index=True)

    class Meta(BaseModel.Meta):
        verbose_name = _('Exam Session')

    def __str__(self):
        return f'Exam [{self.track}] — {self.student.phone_number} — {self.status}'

    @property
    def passing_score(self) -> int:
        return 12  # 60% of 20 questions

    @property
    def is_passed(self) -> bool:
        return self.score is not None and self.score >= self.passing_score


class SessionQuestion(BaseModel):
    """One question as it appears in an exam session (immutable snapshot)."""
    session = models.ForeignKey(ExamSession, on_delete=models.CASCADE, related_name='session_questions')
    question = models.ForeignKey('lms.QuizQuestion', on_delete=models.PROTECT, related_name='session_appearances')
    selected_option = models.CharField(_('Selected Option'), max_length=1, blank=True, default='')
    is_correct = models.BooleanField(_('Correct'), null=True, blank=True)
    answered_at = models.DateTimeField(_('Answered At'), null=True, blank=True)
    sequence_number = models.PositiveSmallIntegerField(_('Sequence'), default=0)

    class Meta(BaseModel.Meta):
        ordering = ['sequence_number']
        unique_together = [['session', 'sequence_number']]


class ProctoringEvent(BaseModel):
    """Records a proctoring event (snapshot, violation, blur, etc.) during B2C exams."""
    EVENT_TYPES = [
        ('SNAPSHOT', 'Scheduled Webcam Snapshot'),
        ('ANOMALY_SNAPSHOT', 'Anomaly-Triggered Snapshot'),
        ('WINDOW_BLUR', 'Window Lost Focus'),
        ('TAB_SWITCH', 'Tab Switch Detected'),
        ('FULLSCREEN_EXIT', 'Fullscreen Exited'),
        ('MOBILE_BLOCKED', 'Mobile Device Blocked'),
        ('SESSION_START', 'Session Started'),
        ('SESSION_END', 'Session Ended'),
    ]
    session = models.ForeignKey(ExamSession, on_delete=models.CASCADE, related_name='proctoring_events')
    event_type = models.CharField(_('Event Type'), max_length=30, choices=EVENT_TYPES, db_index=True)
    snapshot_image = models.ImageField(_('Snapshot'), upload_to='proctoring/snapshots/%Y/%m/', null=True, blank=True)
    metadata = models.JSONField(_('Metadata'), default=dict, blank=True)
    is_violation = models.BooleanField(_('Is Violation'), default=False, db_index=True)

    class Meta(BaseModel.Meta):
        verbose_name = _('Proctoring Event')
        ordering = ['created_at']


# ---------------------------------------------------------------------------
# Certificate Templates & Official Certificates
# ---------------------------------------------------------------------------

class CertificateTemplateType(models.TextChoices):
    STUDENT = "STUDENT", _("Student Enrolled (Cohort Theory Accreditation)")
    GUEST = "GUEST", _("Guest Diagnostic (Provisional Readiness Assessment)")
    ENTERPRISE = "ENTERPRISE", _("Enterprise Driving School (B2B Certified Lab)")


class CertificateTemplate(BaseModel):
    """
    Customizable certificate template for each user category.
    Allows administrators to configure declaration text, confirmation notes,
    official Sifo logo, and insert digital signatures for Training Admin and Sifo Director.
    """
    template_type = models.CharField(
        _("Template Category"),
        max_length=20,
        choices=CertificateTemplateType.choices,
        unique=True,
        db_index=True,
    )
    header_subtitle = models.CharField(
        _("Authority Header / Subtitle"),
        max_length=255,
        default="Republic of Rwanda • Sifo Drive Theory Accreditation",
    )
    title = models.CharField(
        _("Certificate Title"),
        max_length=255,
        default="Certificate of Theory Competence",
    )
    conferral_text = models.CharField(
        _("Conferral Lead-in Text"),
        max_length=255,
        default="This official credential is proudly awarded to",
    )
    course_name = models.CharField(
        _("Course Name"),
        max_length=255,
        default="Rwanda Driving Theory — Provisional License Preparation",
    )
    declaration_text = models.TextField(
        _("Declaration Text"),
        default=(
            "This is to certify that {student_name} has successfully completed the "
            "Rwanda Driving Theory Curriculum and demonstrated proficiency in Traffic Regulations, "
            "Road Signage, and Highway Code Safety with a certified score of {score}/{total_questions}."
        ),
    )
    confirmation_notes = models.TextField(
        _("Confirmation & Accreditation Notes"),
        default=(
            "Certified in accordance with Rwanda National Police traffic theory regulations and "
            "Rwanda Law No 058/2021 on Personal Data Protection. Scan the embedded QR code to verify authenticity."
        ),
    )
    logo_url = models.CharField(
        _("Sifo Drive Logo URL / Asset"),
        max_length=500,
        blank=True,
        default="/assets/logo.svg",
    )
    training_admin_name = models.CharField(
        _("Training Administrator Name"),
        max_length=150,
        default="Training Directorate",
    )
    training_admin_title = models.CharField(
        _("Training Administrator Title"),
        max_length=150,
        default="Head of Training & Pedagogy",
    )
    training_admin_signature = models.TextField(
        _("Training Admin Signature (Base64 / URL)"),
        blank=True,
        default="",
    )
    director_name = models.CharField(
        _("Sifo Director Name"),
        max_length=150,
        default="Sifo Platform Director",
    )
    director_title = models.CharField(
        _("Sifo Director Title"),
        max_length=150,
        default="Managing Director, Sifo Drive",
    )
    director_signature = models.TextField(
        _("Director Signature (Base64 / URL)"),
        blank=True,
        default="",
    )
    is_active = models.BooleanField(_("Is Active"), default=True)

    class Meta(BaseModel.Meta):
        verbose_name = _("Certificate Template")

    def __str__(self):
        return f"Certificate Template [{self.template_type}] — {self.title}"


class Certificate(BaseModel):
    """
    Official certificate auto-generated upon System Admin approval.
    Includes verification hash, public verification URL, scannable QR payload,
    dual signatures, and track-specific start/completion dates.
    """
    certificate_number = models.CharField(
        _("Certificate Serial Number"),
        max_length=50,
        unique=True,
        db_index=True,
    )
    exam_session = models.OneToOneField(
        ExamSession,
        on_delete=models.CASCADE,
        related_name="certificate",
        verbose_name=_("Exam Session"),
    )
    student = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="certificates",
        verbose_name=_("Student"),
    )
    student_name = models.CharField(_("Student Full Name"), max_length=200)
    student_code = models.CharField(_("Student Code / National ID"), max_length=100, blank=True)
    track_type = models.CharField(
        _("Track Type"),
        max_length=20,
        choices=CertificateTemplateType.choices,
        default=CertificateTemplateType.STUDENT,
        db_index=True,
    )
    enterprise_name = models.CharField(
        _("Partner Driving School Name"),
        max_length=255,
        blank=True,
        default="",
        help_text=_("Mentioned explicitly on Enterprise B2B certificates."),
    )
    started_at = models.DateTimeField(
        _("Curriculum Start Date"),
        null=True,
        blank=True,
        help_text=_("Displayed for enrolled students and enterprise, omitted for guests."),
    )
    completed_at = models.DateTimeField(
        _("Completion / Exam Date"),
        null=True,
        blank=True,
    )
    score = models.PositiveSmallIntegerField(_("Score Achieved"))
    total_questions = models.PositiveSmallIntegerField(_("Total Questions"), default=20)
    passing_score = models.PositiveSmallIntegerField(_("Passing Score Threshold"), default=12)
    passed = models.BooleanField(_("Passed Status"), default=True)
    issue_date = models.DateField(_("Issue Date"), auto_now_add=True)
    verification_hash = models.CharField(
        _("SHA-256 Verification Hash"),
        max_length=64,
        db_index=True,
    )
    verification_url = models.CharField(_("Verification URL"), max_length=500)
    template_snapshot = models.JSONField(
        _("Template Snapshot"),
        default=dict,
        blank=True,
        help_text=_("Preserves signatories, wording, and logo at issuance time."),
    )
    is_valid = models.BooleanField(_("Is Valid"), default=True)

    class Meta(BaseModel.Meta):
        verbose_name = _("Certificate")
        ordering = ["-created_at"]

    def __str__(self):
        return f"Certificate {self.certificate_number} — {self.student_name} ({self.score}/20)"
