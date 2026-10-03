import logging
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.core.exceptions import PermissionDeniedException
from apps.core.utils import generate_student_id
from apps.accounts.constants import UserRole
from apps.accounts.models import StudentProfile

User = get_user_model()
logger = logging.getLogger(__name__)


class StudentService:
    """
    Handles student-specific lifecycle events:
      - Guest → Student account upgrade
      - Student ID assignment (after tuition payment)
      - Exam eligibility pre-flight checks
    """

    @classmethod
    def upgrade_guest_to_student(cls, user: User) -> User:
        """
        Upgrade a verified GUEST account to STUDENT.

        Pre-conditions (validated in the serializer / view before this is called):
          - user.role == GUEST
          - user.status == ACTIVE  (phone already verified)
          - user.privacy_policy_accepted == True  (serializer enforces this)

        Post-upgrade state:
          - role → STUDENT
          - Student ID NOT yet assigned (assigned after tuition payment)
          - StudentProfile created (ready to receive enrollment details)
        """
        if user.role == UserRole.STUDENT:
            return user  # Idempotent

        if user.role != UserRole.GUEST:
            raise PermissionDeniedException(
                "Only GUEST accounts can be upgraded to STUDENT."
            )

        user.role = UserRole.STUDENT
        user.save(update_fields=["role"])

        # Ensure extended profile exists
        StudentProfile.objects.get_or_create(user=user)

        # Auto-enroll in default open cohort if not already enrolled in a cohort
        if not user.enrolled_cohorts.exists():
            try:
                from apps.live_classes.services import CohortService
                CohortService.enroll_student_in_default_open_cohort(user)
            except Exception as e:
                logger.warning("Could not auto-enroll upgraded student into open cohort: %s", e)

        logger.info(
            "Guest upgraded to Student | user=%s",
            str(user.id)[:8],
        )
        return user

    @classmethod
    def assign_student_id(cls, user: User) -> str:
        """
        Generate and assign a unique Student ID.
        Called by the payments app after tuition payment webhook confirms success.

        Format: SIFO-STU-{YEAR}-{SEQUENCE:04d}
        Example: SIFO-STU-2026-0042
        """
        if user.role != UserRole.STUDENT:
            raise ValueError("Only STUDENT role users can receive a Student ID.")

        if user.student_id:
            return user.student_id  # Already assigned — idempotent

        cohort = user.cohorts.first()
        student_id = generate_student_id(cohort=cohort)
        user.student_id = student_id
        user.save(update_fields=["student_id"])

        # Ensure enrollment profile exists with date set
        StudentProfile.objects.update_or_create(
            user=user,
            defaults={"enrollment_date": timezone.now().date()},
        )

        logger.info("Student ID assigned | %s → %s", str(user.id)[:8], student_id)
        return student_id

    @classmethod
    def check_exam_eligibility(cls, user: User) -> dict:
        """
        Verify a student meets all B2C exam prerequisites:
          1. Tuition paid and active
          2. ≥ 75% live class attendance
          3. 100% foundational module completion

        Returns a structured dict with eligibility status and per-criterion detail.
        This dict drives the eligibility breakdown on the student dashboard.
        """
        from apps.payments.services import PaymentService
        from apps.live_classes.services import AttendanceService
        from apps.lms.services import ProgressService

        reasons = []
        eligible = True

        tuition_paid = PaymentService.has_active_tuition(user)
        if not tuition_paid:
            eligible = False
            reasons.append("Tuition fee has not been paid.")

        attendance_rate = AttendanceService.get_attendance_rate(user)
        if attendance_rate < 0.75:
            eligible = False
            reasons.append(
                f"Live class attendance is {attendance_rate:.0%} — minimum required is 75%."
            )

        module_completion = ProgressService.get_foundational_completion(user)
        if module_completion < 1.0:
            eligible = False
            reasons.append(
                f"Foundational modules are {module_completion:.0%} complete — 100% required."
            )

        return {
            "eligible": eligible,
            "reasons": reasons,
            "criteria": {
                "tuition_paid": tuition_paid,
                "attendance_rate": round(attendance_rate, 4),
                "module_completion": round(module_completion, 4),
            },
        }
