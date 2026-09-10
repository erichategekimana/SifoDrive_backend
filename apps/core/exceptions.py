"""
apps/core/exceptions.py
========================
Typed exception hierarchy and the custom DRF exception handler.

Rules:
  1. Services raise specific typed exceptions (never generic ValueError/Exception).
  2. Views never catch exceptions — the handler converts them to JSON responses.
  3. Every exception class carries a machine-readable `default_code` so the
     frontend can branch on error type without parsing message strings.
  4. The response envelope is always:
       {
           "success": false,
           "error": {
               "code":    "payment_failed",         ← machine-readable
               "message": "Payment processing...",  ← human-readable
               "details": { "field": ["error"] }    ← only for validation errors
           }
       }
"""

import logging

from django.utils.translation import gettext_lazy as _
from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_default_handler

logger = logging.getLogger(__name__)


# ===========================================================================
# Base Exception
# ===========================================================================

class SifoDriveException(APIException):
    """
    Root exception for all Sifo Drive business logic errors.

    Usage:
        raise PaymentFailedException("MTN MoMo webhook timeout.")
        raise ExamNotEligibleException(extra={"attendance_rate": 0.62})

    The `extra` kwarg is for internal server-side context (e.g. debug info).
    It is NEVER included in the client-facing response.
    """

    status_code   = status.HTTP_400_BAD_REQUEST
    default_detail = _("An unexpected error occurred.")
    default_code   = "sifo_error"

    def __init__(self, detail=None, code=None, extra: dict | None = None):
        super().__init__(detail=detail, code=code)
        self.extra = extra or {}


# ===========================================================================
# Authentication & Authorization
# ===========================================================================

class AuthenticationFailedException(SifoDriveException):
    """Invalid or expired credentials."""
    status_code    = status.HTTP_401_UNAUTHORIZED
    default_detail = _("Authentication credentials are invalid or have expired.")
    default_code   = "authentication_failed"


class OTPExpiredException(SifoDriveException):
    """OTP code has passed its expiry window."""
    status_code    = status.HTTP_400_BAD_REQUEST
    default_detail = _("The OTP code has expired. Please request a new one.")
    default_code   = "otp_expired"


class OTPInvalidException(SifoDriveException):
    """OTP code does not match (wrong code or already used)."""
    status_code    = status.HTTP_400_BAD_REQUEST
    default_detail = _("The OTP code is incorrect.")
    default_code   = "otp_invalid"


class OTPRateLimitException(SifoDriveException):
    """Too many OTP requests in the rate-limit window."""
    status_code    = status.HTTP_429_TOO_MANY_REQUESTS
    default_detail = _("Too many OTP requests. Please wait before requesting a new code.")
    default_code   = "otp_rate_limit"


class PermissionDeniedException(SifoDriveException):
    """User's role is insufficient for this action."""
    status_code    = status.HTTP_403_FORBIDDEN
    default_detail = _("You do not have permission to perform this action.")
    default_code   = "permission_denied"


class ConsentRequiredException(SifoDriveException):
    """
    Raised when an action requires consent that hasn't been given yet.
    Use the `consent_type` extra field to tell the frontend which modal to show.

    Example:
        raise ConsentRequiredException(
            "Privacy Policy acceptance required.",
            extra={"consent_type": "privacy_policy"}
        )
    """
    status_code    = status.HTTP_403_FORBIDDEN
    default_detail = _("Your consent is required before proceeding.")
    default_code   = "consent_required"


class TokenExpiredException(SifoDriveException):
    """JWT access token has expired."""
    status_code    = status.HTTP_401_UNAUTHORIZED
    default_detail = _("Your session has expired. Please log in again.")
    default_code   = "token_expired"


# ===========================================================================
# User / Account
# ===========================================================================

class UserNotFoundException(SifoDriveException):
    """Requested user account does not exist."""
    status_code    = status.HTTP_404_NOT_FOUND
    default_detail = _("User account not found.")
    default_code   = "user_not_found"


class UserAlreadyExistsException(SifoDriveException):
    """Duplicate registration: phone or email already taken."""
    status_code    = status.HTTP_409_CONFLICT
    default_detail = _("An account with this phone number or email already exists.")
    default_code   = "user_already_exists"


class AccountSuspendedException(SifoDriveException):
    """A suspended account attempted a protected action."""
    status_code    = status.HTTP_403_FORBIDDEN
    default_detail = _("Your account has been suspended. Please contact support.")
    default_code   = "account_suspended"


class AccountNotVerifiedException(SifoDriveException):
    """Account phone number has not been verified yet."""
    status_code    = status.HTTP_403_FORBIDDEN
    default_detail = _("Please verify your phone number before proceeding.")
    default_code   = "account_not_verified"


class InvalidRoleTransitionException(SifoDriveException):
    """An invalid role change was attempted (e.g. STUDENT → GUEST)."""
    status_code    = status.HTTP_400_BAD_REQUEST
    default_detail = _("This account role transition is not permitted.")
    default_code   = "invalid_role_transition"


# ===========================================================================
# Payments
# ===========================================================================

class PaymentFailedException(SifoDriveException):
    """MoMo payment initiation or confirmation webhook failed."""
    status_code    = status.HTTP_402_PAYMENT_REQUIRED
    default_detail = _("Payment processing failed. Please try again.")
    default_code   = "payment_failed"


class PaymentAlreadyProcessedException(SifoDriveException):
    """Idempotency check: this transaction ID was already recorded."""
    status_code    = status.HTTP_409_CONFLICT
    default_detail = _("This transaction has already been processed.")
    default_code   = "payment_already_processed"


class InsufficientFundsException(SifoDriveException):
    """MoMo wallet balance is below the required amount."""
    status_code    = status.HTTP_402_PAYMENT_REQUIRED
    default_detail = _("Insufficient Mobile Money balance. Please top up and try again.")
    default_code   = "insufficient_funds"


class PaymentProviderUnavailableException(SifoDriveException):
    """The MoMo provider API is unreachable or returned an error."""
    status_code    = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = _("The payment provider is temporarily unavailable. Please try again shortly.")
    default_code   = "payment_provider_unavailable"


# ===========================================================================
# Examinations
# ===========================================================================

class ExamNotEligibleException(SifoDriveException):
    """
    Student does not meet exam eligibility criteria.
    Pass the eligibility breakdown in `extra` for the dashboard.
    """
    status_code    = status.HTTP_403_FORBIDDEN
    default_detail = _(
        "You do not meet the exam eligibility requirements. "
        "Ensure tuition is paid, live class attendance is ≥75%, "
        "and all foundational modules are completed."
    )
    default_code   = "exam_not_eligible"


class ExamAlreadyActiveException(SifoDriveException):
    """A second concurrent exam session was attempted."""
    status_code    = status.HTTP_409_CONFLICT
    default_detail = _("You already have an active exam session. Only one session is allowed at a time.")
    default_code   = "exam_already_active"


class ExamSessionExpiredException(SifoDriveException):
    """Student attempted to submit after the 20-minute time limit."""
    status_code    = status.HTTP_410_GONE
    default_detail = _("Your exam session has expired. The 20-minute time limit was exceeded.")
    default_code   = "exam_session_expired"


class DeviceNotAllowedException(SifoDriveException):
    """Mobile or tablet device attempted B2C exam access."""
    status_code    = status.HTTP_403_FORBIDDEN
    default_detail = _(
        "Exam access is restricted to laptops and desktops only. "
        "Mobile phones and tablets are not permitted."
    )
    default_code   = "device_not_allowed"


class ExamFlaggedForReviewException(SifoDriveException):
    """Exam auto-flagged due to proctoring integrity violations."""
    status_code    = status.HTTP_403_FORBIDDEN
    default_detail = _("Your exam session has been flagged for review due to integrity violations.")
    default_code   = "exam_flagged"


class ExamNotFoundException(SifoDriveException):
    """Requested exam session does not exist."""
    status_code    = status.HTTP_404_NOT_FOUND
    default_detail = _("Exam session not found.")
    default_code   = "exam_not_found"


# ===========================================================================
# Irembo Booking
# ===========================================================================

class BookingNotFoundException(SifoDriveException):
    """Booking ticket cannot be found."""
    status_code    = status.HTTP_404_NOT_FOUND
    default_detail = _("Booking record not found.")
    default_code   = "booking_not_found"


class BookingAlreadyProcessedException(SifoDriveException):
    """Agent tried to lock a ticket already in PROCESSING state."""
    status_code    = status.HTTP_409_CONFLICT
    default_detail = _("This booking ticket is already being processed by another agent.")
    default_code   = "booking_already_processing"


class BookingSlotsExhaustedException(SifoDriveException):
    """Irembo slots ran out before the ticket was processed."""
    status_code    = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = _(
        "Official Irembo slots have been exhausted for this batch. "
        "You may retain your priority for the next batch or request a refund."
    )
    default_code   = "slots_exhausted"


class InvalidBookingStateTransitionException(SifoDriveException):
    """An illegal booking state machine transition was attempted."""
    status_code    = status.HTTP_400_BAD_REQUEST
    default_detail = _("This booking state transition is not permitted.")
    default_code   = "invalid_booking_state"


# ===========================================================================
# LMS
# ===========================================================================

class ContentNotFoundException(SifoDriveException):
    """Requested course content (lesson, module, course) was not found."""
    status_code    = status.HTTP_404_NOT_FOUND
    default_detail = _("The requested content could not be found.")
    default_code   = "content_not_found"


class AccessDeniedException(SifoDriveException):
    """Guest attempted to access student-only content."""
    status_code    = status.HTTP_403_FORBIDDEN
    default_detail = _("This content requires full student enrollment. Please upgrade your account.")
    default_code   = "access_denied_student_only"


class ContentNotPublishedException(SifoDriveException):
    """Learner tried to access unpublished (draft) content."""
    status_code    = status.HTTP_404_NOT_FOUND
    default_detail = _("This content is not yet available.")
    default_code   = "content_not_published"


# ===========================================================================
# Generic / Infrastructure
# ===========================================================================

class ResourceNotFoundException(SifoDriveException):
    """Generic 404 for any resource that cannot be found."""
    status_code    = status.HTTP_404_NOT_FOUND
    default_detail = _("The requested resource could not be found.")
    default_code   = "not_found"


class ConflictException(SifoDriveException):
    """Generic 409 for duplicate / conflict scenarios."""
    status_code    = status.HTTP_409_CONFLICT
    default_detail = _("A conflict occurred with an existing resource.")
    default_code   = "conflict"


class ServiceUnavailableException(SifoDriveException):
    """External service (SMS gateway, MoMo API, etc.) is down."""
    status_code    = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = _("A required service is temporarily unavailable. Please try again later.")
    default_code   = "service_unavailable"


class RateLimitException(SifoDriveException):
    """Generic rate limit exceeded."""
    status_code    = status.HTTP_429_TOO_MANY_REQUESTS
    default_detail = _("Too many requests. Please slow down and try again shortly.")
    default_code   = "rate_limit_exceeded"


# ===========================================================================
# Custom DRF Exception Handler
# ===========================================================================

def custom_exception_handler(exc, context) -> Response | None:
    """
    Global DRF exception handler.

    Converts ALL exceptions (DRF-native + our custom ones) into the
    standard Sifo Drive JSON envelope:

        {
            "success": false,
            "error": {
                "code":    "payment_failed",
                "message": "Payment processing failed.",
                "details": { "amount": ["This field is required."] }  ← validation only
            }
        }

    Configure in settings:
        REST_FRAMEWORK = {
            "EXCEPTION_HANDLER": "apps.core.exceptions.custom_exception_handler"
        }
    """
    response = drf_default_handler(exc, context)

    if response is None:
        # Unhandled exception — let Django's 500 handler deal with it
        logger.error(
            "Unhandled exception in %s: %s",
            _view_name(context),
            exc,
            exc_info=True,
        )
        return None

    # ── Build a clean error code ──────────────────────────────────────────
    code = _resolve_code(exc, response)

    # ── Build the standardised payload ───────────────────────────────────
    error_block: dict = {
        "code":    code,
        "message": _extract_message(response.data),
    }

    # Include field-level validation details for 400 responses
    if isinstance(exc, ValidationError) or (
        response.status_code == 400
        and isinstance(response.data, dict)
        and any(isinstance(v, list) for v in response.data.values())
    ):
        # Don't overwrite 'details' if the message already consumed the data
        raw = response.data
        if isinstance(raw, dict) and "detail" not in raw:
            error_block["details"] = raw

    response.data = {
        "success": False,
        "error":   error_block,
    }

    # ── Logging ──────────────────────────────────────────────────────────
    if response.status_code >= 500:
        logger.error(
            "5xx in %s [%s]: %s",
            _view_name(context),
            response.status_code,
            exc,
            exc_info=True,
        )
    elif response.status_code >= 400:
        logger.warning(
            "4xx in %s [%s %s]: %s",
            _view_name(context),
            response.status_code,
            code,
            exc,
        )

    return response


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _resolve_code(exc, response) -> str:
    """Resolve the machine-readable error code from the exception."""
    # Custom SifoDriveException — use its code
    if isinstance(exc, SifoDriveException):
        return exc.default_code

    # DRF built-in exceptions have a .default_code on the detail ErrorDetail
    if hasattr(exc, "detail"):
        detail = exc.detail
        if hasattr(detail, "code"):
            return str(detail.code)
        if isinstance(detail, dict):
            for v in detail.values():
                if isinstance(v, list) and v and hasattr(v[0], "code"):
                    return str(v[0].code)

    # Fallback based on status code
    return {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        405: "method_not_allowed",
        409: "conflict",
        429: "rate_limit_exceeded",
        500: "server_error",
        503: "service_unavailable",
    }.get(response.status_code, "error")


def _extract_message(data) -> str:
    """Collapse DRF error data into a single human-readable string."""
    if isinstance(data, dict):
        if "detail" in data:
            return str(data["detail"])
        # First field's first error message
        for value in data.values():
            if isinstance(value, list) and value:
                return str(value[0])
            if isinstance(value, str):
                return value
    if isinstance(data, list) and data:
        return str(data[0])
    return str(data)


def _view_name(context) -> str:
    view = context.get("view")
    if view is None:
        return "unknown"
    return type(view).__name__
