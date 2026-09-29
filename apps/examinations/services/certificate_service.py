import hashlib
import logging
import uuid

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.examinations.models import (
    Certificate,
    CertificateTemplate,
    CertificateTemplateType,
    ExamSession,
)

logger = logging.getLogger(__name__)


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
