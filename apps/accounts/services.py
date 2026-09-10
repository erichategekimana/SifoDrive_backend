"""
apps/accounts/services.py
==========================
Business logic layer for account operations.
Views delegate to these service classes — keeping views thin and testable.

Classes:
  AuthService     — OTP generation, verification, JWT-ready login flow
  UserService     — CRUD, role transitions, profile management
  StudentService  — Enrollment, Student ID assignment, eligibility checks, upgrade
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.core.exceptions import (
    AccountSuspendedException,
    OTPExpiredException,
    OTPInvalidException,
    OTPRateLimitException,
    PermissionDeniedException,
    UserNotFoundException,
)
from apps.core.utils import generate_numeric_otp, generate_student_id, normalize_phone_number
from .constants import AccountStatus, UserRole
from .models import OTPVerification, StudentProfile

User = get_user_model()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Authentication Service
# ---------------------------------------------------------------------------

class AuthService:
    """
    Handles phone-based OTP authentication flow.

    Registration flow:
      1. POST /auth/register/guest/ or /auth/register/student/
         → User created in PENDING_VERIFICATION
         → OTP automatically sent via _send_otp_sms()

      2. POST /auth/otp/verify/ { purpose: "REGISTRATION" }
         → OTP verified, account moves to ACTIVE
         → JWT tokens returned

    Login flow (for already-active accounts):
      1. POST /auth/otp/request/ { purpose: "LOGIN" }
      2. POST /auth/otp/verify/ { purpose: "LOGIN" }
         → JWT tokens returned
    """

    OTP_LENGTH = 6
    MAX_ATTEMPTS = 5

    @classmethod
    def request_otp(cls, phone_number: str, purpose: str = "LOGIN") -> OTPVerification:
        """
        Generate a new OTP for the given phone number and purpose.
        Enforces a per-hour rate limit per COMPLIANCE settings.

        Returns the OTPVerification instance (the raw OTP is only visible
        inside this method and is passed directly to the SMS task).

        Raises: OTPRateLimitException if the hourly limit is exceeded.
        """
        limit = settings.COMPLIANCE.get("OTP_ATTEMPT_LIMIT", 5)
        one_hour_ago = timezone.now() - timedelta(hours=1)

        recent_count = OTPVerification.objects.filter(
            phone_number=phone_number,
            purpose=purpose,
            created_at__gte=one_hour_ago,
        ).count()

        if recent_count >= limit:
            raise OTPRateLimitException()

        # Invalidate any active OTPs for this phone + purpose before issuing a new one
        OTPVerification.objects.filter(
            phone_number=phone_number,
            purpose=purpose,
            is_used=False,
        ).update(is_used=True)

        raw_otp = generate_numeric_otp(cls.OTP_LENGTH)
        otp_instance = OTPVerification.objects.create(
            phone_number=phone_number,
            otp_hash=OTPVerification.hash_otp(raw_otp),
            purpose=purpose,
            expires_at=timezone.now() + timedelta(minutes=settings.OTP_EXPIRY_MINUTES),
        )

        cls._send_otp_sms(phone_number, raw_otp, purpose)

        logger.info(
            "OTP issued | phone=…%s purpose=%s",
            phone_number[-4:],
            purpose,
        )
        return otp_instance

    @classmethod
    def verify_otp(cls, phone_number: str, raw_otp: str, purpose: str = "LOGIN") -> User:
        """
        Validate a submitted OTP code.

        On success:
          - Marks the OTP as consumed.
          - Activates the user account if it is still PENDING_VERIFICATION.
          - Returns the User object ready for JWT token generation.

        Raises: OTPInvalidException, OTPExpiredException,
                OTPRateLimitException, UserNotFoundException,
                AccountSuspendedException.
        """
        try:
            otp = OTPVerification.objects.filter(
                phone_number=phone_number,
                purpose=purpose,
                is_used=False,
            ).latest("created_at")
        except OTPVerification.DoesNotExist:
            raise OTPInvalidException(
                "No active OTP found for this phone number and purpose."
            )

        if otp.attempt_count >= cls.MAX_ATTEMPTS:
            raise OTPRateLimitException()

        if otp.is_expired:
            raise OTPExpiredException()

        submitted_hash = OTPVerification.hash_otp(raw_otp)
        # Constant-time comparison — prevents timing attacks
        import hmac as _hmac
        if not _hmac.compare_digest(submitted_hash, otp.otp_hash):
            otp.increment_attempts()
            remaining = cls.MAX_ATTEMPTS - otp.attempt_count
            raise OTPInvalidException(
                f"Incorrect code. {remaining} attempt(s) remaining."
            )

        otp.mark_used()

        try:
            user = User.objects.get(phone_number=phone_number)
        except User.DoesNotExist:
            raise UserNotFoundException()

        if user.is_suspended:
            raise AccountSuspendedException()

        # First-time verification → activate the account
        if user.status == AccountStatus.PENDING_VERIFICATION:
            user.activate()
            logger.info(
                "Account activated | user=%s role=%s",
                str(user.id)[:8],
                user.role,
            )

        logger.info(
            "OTP verified | user=%s purpose=%s",
            str(user.id)[:8],
            purpose,
        )
        return user

    @staticmethod
    def _send_otp_sms(phone_number: str, raw_otp: str, purpose: str) -> None:
        """Queue SMS dispatch via Celery (non-blocking)."""
        try:
            from apps.notifications.tasks import send_otp_sms_task
            send_otp_sms_task.delay(phone_number, raw_otp, purpose)
        except Exception as exc:
            # Log but never crash the request — SMS failure is non-fatal at the API level
            logger.error(
                "SMS queue failure | phone=…%s purpose=%s error=%s",
                phone_number[-4:],
                purpose,
                exc,
            )


# ---------------------------------------------------------------------------
# User Management Service
# ---------------------------------------------------------------------------

class UserService:
    """CRUD and lifecycle operations for user accounts."""

    @classmethod
    def get_by_phone(cls, phone_number: str) -> User:
        """Fetch a user by phone number. Raises UserNotFoundException if not found."""
        normalized = normalize_phone_number(phone_number)
        if not normalized:
            raise UserNotFoundException()
        try:
            return User.objects.get(phone_number=normalized)
        except User.DoesNotExist:
            raise UserNotFoundException()

    @classmethod
    def get_by_id(cls, user_id: str) -> User:
        """Fetch a user by UUID. Raises UserNotFoundException if not found."""
        try:
            return User.objects.get(id=user_id)
        except User.DoesNotExist:
            raise UserNotFoundException()

    @classmethod
    def suspend_user(cls, user: User, suspended_by: User) -> User:
        """Suspend a user account. Logs the action."""
        user.suspend()
        logger.warning(
            "User suspended | target=%s by_admin=%s",
            str(user.id)[:8],
            str(suspended_by.id)[:8],
        )
        return user

    @classmethod
    def promote_to_role(cls, user: User, new_role: str, promoted_by: User) -> User:
        """
        Change a user's role. Only SYSTEM_ADMIN is authorised to call this.
        Records an immutable audit log entry.
        """
        old_role = user.role
        user.role = new_role
        user.save(update_fields=["role"])

        from apps.audit.services import AuditService
        AuditService.log_role_change(
            target_user=user,
            old_role=old_role,
            new_role=new_role,
            performed_by=promoted_by,
        )
        return user


# ---------------------------------------------------------------------------
# Student Enrollment Service
# ---------------------------------------------------------------------------

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

        student_id = generate_student_id()
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
