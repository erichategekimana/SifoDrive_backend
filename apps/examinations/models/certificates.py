from django.db import models
from django.utils.translation import gettext_lazy as _
from apps.core.models import BaseModel
from apps.examinations.models.choices import CertificateTemplateType
from apps.examinations.models.sessions import ExamSession


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
        app_label = 'examinations'
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
        app_label = 'examinations'
        verbose_name = _("Certificate")
        ordering = ["-created_at"]

    def __str__(self):
        return f"Certificate {self.certificate_number} — {self.student_name} ({self.score}/20)"
