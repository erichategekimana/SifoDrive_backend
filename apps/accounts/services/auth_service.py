import hmac as _hmac
import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.core.exceptions import (
    AccountSuspendedException,
    AuthenticationFailedException,
    OTPExpiredException,
    OTPInvalidException,
    OTPRateLimitException,
    SifoDriveException,
    UserNotFoundException,
)
from apps.core.utils import generate_numeric_otp, normalize_phone_number
from apps.accounts.constants import AccountStatus
from apps.accounts.models import OTPVerification

User = get_user_model()
logger = logging.getLogger(__name__)


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
    def authenticate_by_password(cls, phone_number: str, password: str) -> User:
        """
        Authenticate a user using phone number and password (no OTP required for login).
        Applicable to all users (SYSTEM_ADMIN, TUTOR, STUDENT, GUEST).
        """
        normalized = normalize_phone_number(phone_number)
        if not normalized:
            raise AuthenticationFailedException("Invalid phone number or password.")

        try:
            user = User.objects.get(phone_number=normalized)
        except User.DoesNotExist:
            raise AuthenticationFailedException("Invalid phone number or password.")

        if not user.check_password(password):
            raise AuthenticationFailedException("Invalid phone number or password.")

        if user.status == AccountStatus.SUSPENDED:
            raise AccountSuspendedException("Your account has been suspended. Please contact support.")

        if user.status == AccountStatus.PENDING_VERIFICATION:
            raise SifoDriveException(
                "Account is pending verification. Please verify your phone number with the OTP received during registration.",
                code="account_pending_verification",
            )

        user.last_login = timezone.now()
        user.save(update_fields=["last_login"])
        return user

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
            if user.role == UserRole.STUDENT and not user.enrolled_cohorts.exists():
                try:
                    from apps.live_classes.services import CohortService
                    CohortService.enroll_student_in_default_open_cohort(user)
                except Exception as e:
                    logger.warning("Could not auto-enroll verified student into open cohort: %s", e)

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
