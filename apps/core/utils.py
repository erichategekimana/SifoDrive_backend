"""
apps/core/utils.py
===================
Shared utility functions and classes across all Sifo Drive apps.

Sections:
  PIIEncryptor            — AES-256 Fernet encryption for National ID columns
  PhoneNumberUtils        — E.164 normalization, MoMo provider detection, validation
  OTPUtils                — Cryptographically secure OTP generation
  IDGenerators            — Student ID, Booking ticket number generators
  SecurityUtils           — HMAC webhook signature verification, token generation
  DateTimeUtils           — Timezone-aware date helpers for Rwandan business hours
"""

import hashlib
import hmac
import secrets
import string
from datetime import date, datetime, time
from typing import Optional
from zoneinfo import ZoneInfo

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.utils import timezone


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RWANDA_TZ = ZoneInfo("Africa/Kigali")


# ===========================================================================
# PII Encryption — AES-256 via Fernet
# ===========================================================================

class PIIEncryptor:
    """
    AES-256-CBC (Fernet) encryption / decryption for PII fields.

    Used for:
      - User.national_id_encrypted   (Indangamuntu — 16-digit NID)
      - BookingOrder.national_id_encrypted

    Compliance: Rwanda Law No 058/2021, Article 40.
    Key source: settings.PII_ENCRYPTION_KEY (base64-url Fernet key).

    Usage:
        enc = get_pii_encryptor()
        token = enc.encrypt("1199800123456789")
        nid   = enc.decrypt(token)          # "1199800123456789"
        bad   = enc.decrypt("corrupted")    # None — never raises
    """

    def __init__(self) -> None:
        key = getattr(settings, "PII_ENCRYPTION_KEY", None)
        if not key:
            raise ImproperlyConfigured(
                "PII_ENCRYPTION_KEY is not set in settings. "
                "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )
        if isinstance(key, str):
            key = key.encode()
        self._fernet = Fernet(key)

    def encrypt(self, plaintext: str) -> str:
        """
        Encrypt plaintext PII.
        Returns a URL-safe base64 Fernet token (str).
        Empty/None input is returned unchanged.
        """
        if not plaintext:
            return plaintext or ""
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")

    def decrypt(self, ciphertext: str) -> Optional[str]:
        """
        Decrypt Fernet ciphertext.
        Returns None on any failure — never raises.
        Callers must handle None as "decryption not possible".
        """
        if not ciphertext:
            return None
        try:
            return self._fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
        except (InvalidToken, Exception):
            # Do NOT log the ciphertext — it is still sensitive even if invalid
            return None

    def re_encrypt(self, ciphertext: str) -> Optional[str]:
        """
        Decrypt then re-encrypt with the current key.
        Useful during key rotation.
        """
        plaintext = self.decrypt(ciphertext)
        if plaintext is None:
            return None
        return self.encrypt(plaintext)


# Module-level singleton
_pii_encryptor: Optional[PIIEncryptor] = None


def get_pii_encryptor() -> PIIEncryptor:
    """Return the shared PIIEncryptor singleton (lazy initialised)."""
    global _pii_encryptor
    if _pii_encryptor is None:
        _pii_encryptor = PIIEncryptor()
    return _pii_encryptor


# Convenience shortcut
def ImproperlyConfigured(msg: str):
    from django.core.exceptions import ImproperlyConfigured as _IC
    return _IC(msg)


# ===========================================================================
# Phone Number Utilities
# ===========================================================================

class PhoneNumberUtils:
    """
    Utilities for Rwandan phone numbers.
    All methods that return a normalized number use E.164 format (+250XXXXXXXXX).
    """

    # Current Rwanda MoMo prefix mappings (as of 2025)
    _MTN_PREFIXES    = {"078", "079", "072"}
    _AIRTEL_PREFIXES = {"073", "074"}

    @classmethod
    def normalize(cls, phone: str, default_region: str = "RW") -> Optional[str]:
        """
        Parse and normalize a phone number to E.164 (+250XXXXXXXXX).
        Returns None if the number is invalid for Rwanda.

        Accepts:
          0781234567      → +250781234567
          250781234567    → +250781234567
          +250781234567   → +250781234567
        """
        import phonenumbers

        try:
            parsed = phonenumbers.parse(phone, default_region)
            if phonenumbers.is_valid_number(parsed):
                return phonenumbers.format_number(
                    parsed, phonenumbers.PhoneNumberFormat.E164
                )
            return None
        except phonenumbers.NumberParseException:
            return None

    @classmethod
    def is_valid(cls, phone: str) -> bool:
        return cls.normalize(phone) is not None

    @classmethod
    def detect_momo_provider(cls, phone: str) -> Optional[str]:
        """
        Return 'MTN' or 'AIRTEL' based on phone prefix.
        Returns None if the prefix is unrecognised or the number is invalid.
        """
        normalized = cls.normalize(phone)
        if not normalized:
            return None
        # Strip +250 country code → local 10-digit number
        local = normalized[4:]       # e.g. 0781234567
        prefix = local[:3]           # e.g. 078
        if prefix in cls._MTN_PREFIXES:
            return "MTN"
        if prefix in cls._AIRTEL_PREFIXES:
            return "AIRTEL"
        return None

    @classmethod
    def obfuscate(cls, phone: str, visible_digits: int = 4) -> str:
        """
        Return a privacy-safe version of a phone number for display/logging.
        Example: +250781234567 → +250***4567
        """
        if not phone or len(phone) < visible_digits:
            return phone
        return phone[:-visible_digits].replace(phone[:-visible_digits], "*" * len(phone[:-visible_digits])) + phone[-visible_digits:]


# Module-level convenience wrappers
def normalize_phone_number(phone: str, country_code: str = "RW") -> Optional[str]:
    return PhoneNumberUtils.normalize(phone, country_code)


def detect_momo_provider(phone: str) -> Optional[str]:
    return PhoneNumberUtils.detect_momo_provider(phone)


# ===========================================================================
# OTP Utilities
# ===========================================================================

class OTPUtils:
    """Cryptographically secure OTP generation helpers."""

    @staticmethod
    def generate_numeric(length: int = 6) -> str:
        """
        Generate a cryptographically secure numeric OTP.
        Uses secrets.choice — never random.randint.
        """
        if length < 4:
            raise ValueError("OTP length must be at least 4 digits.")
        return "".join(secrets.choice(string.digits) for _ in range(length))

    @staticmethod
    def generate_alphanumeric(length: int = 8) -> str:
        """Generate a mixed-case alphanumeric token (for email verification, etc.)."""
        alphabet = string.ascii_letters + string.digits
        return "".join(secrets.choice(alphabet) for _ in range(length))


def generate_numeric_otp(length: int = 6) -> str:
    """Convenience wrapper for OTPUtils.generate_numeric()."""
    return OTPUtils.generate_numeric(length)


# ===========================================================================
# ID Generators
# ===========================================================================

def generate_student_id(year: Optional[int] = None, sequence: Optional[int] = None) -> str:
    """
    Generate a unique Sifo Drive Student ID.
    Format: SIFO-STU-{YEAR}-{SEQ:04d}
    Example: SIFO-STU-2026-0042

    Args:
        year:     Academic year (default: current year).
        sequence: Enrollment sequence (default: auto-assigned from DB count).

    Notes:
        - The sequence is advisory — always check uniqueness after generation.
        - Assigned by StudentService.assign_student_id() after payment confirmation.
    """
    if year is None:
        year = timezone.now().year

    if sequence is None:
        from apps.accounts.models import User
        count = User.objects.filter(
            role="STUDENT",
            created_at__year=year,
        ).count()
        sequence = count + 1

    return f"SIFO-STU-{year}-{sequence:04d}"


def generate_booking_ticket(prefix: str = "SIFO-BKG") -> str:
    """
    Generate a unique booking ticket number.
    Format: SIFO-BKG-{6 uppercase alphanumeric chars}
    Example: SIFO-BKG-A3F9X2
    """
    alphabet = string.ascii_uppercase + string.digits
    suffix = "".join(secrets.choice(alphabet) for _ in range(6))
    return f"{prefix}-{suffix}"


# ===========================================================================
# Security Utilities
# ===========================================================================

class SecurityUtils:
    """
    Security-critical utilities: webhook signature verification,
    secure token generation, constant-time comparisons.
    """

    @staticmethod
    def verify_webhook_signature(payload: bytes, signature: str, secret: str) -> bool:
        """
        Verify an HMAC-SHA256 webhook signature.
        Used to authenticate incoming MoMo payment callbacks.

        Args:
            payload:   Raw request body bytes.
            signature: The signature header value (hex digest).
            secret:    The shared secret configured with the payment provider.

        Returns True only if the signature is valid.
        Uses hmac.compare_digest (constant-time) to prevent timing attacks.
        """
        expected = hmac.new(
            key=secret.encode("utf-8"),
            msg=payload,
            digestmod=hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    @staticmethod
    def generate_secure_token(n_bytes: int = 32) -> str:
        """
        Generate a URL-safe cryptographically secure random token.
        Used for password reset links, email verification tokens, etc.
        """
        return secrets.token_urlsafe(n_bytes)

    @staticmethod
    def sha256_hex(data: str) -> str:
        """Return the SHA-256 hex digest of a UTF-8 string."""
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    @staticmethod
    def constant_time_equal(a: str, b: str) -> bool:
        """Compare two strings in constant time (prevents timing attacks)."""
        return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


# Convenience wrappers
def verify_webhook_signature(payload: bytes, signature: str, secret: str) -> bool:
    return SecurityUtils.verify_webhook_signature(payload, signature, secret)


# ===========================================================================
# Date / Time Utilities
# ===========================================================================

class DateTimeUtils:
    """
    Timezone-aware date/time helpers calibrated to Rwanda (Africa/Kigali, UTC+2).
    """

    RWANDA_TZ = RWANDA_TZ
    BUSINESS_START = time(8, 0)   # 08:00 local time
    BUSINESS_END   = time(17, 0)  # 17:00 local time

    @classmethod
    def now_rwanda(cls) -> datetime:
        """Return the current datetime in Kigali local time."""
        return timezone.now().astimezone(cls.RWANDA_TZ)

    @classmethod
    def today_rwanda(cls) -> date:
        """Return today's date in Kigali local time."""
        return cls.now_rwanda().date()

    @classmethod
    def is_business_hours(cls) -> bool:
        """
        Returns True if the current Kigali time is within business hours
        (Mon–Fri, 08:00–17:00).
        """
        now = cls.now_rwanda()
        if now.weekday() >= 5:  # Saturday=5, Sunday=6
            return False
        return cls.BUSINESS_START <= now.time() <= cls.BUSINESS_END

    @classmethod
    def days_until(cls, target_date: date) -> int:
        """Return the number of days from today (Kigali) until target_date."""
        return (target_date - cls.today_rwanda()).days

    @classmethod
    def format_for_sms(cls, dt: datetime) -> str:
        """Format a datetime for inclusion in an SMS (concise, local time)."""
        local = dt.astimezone(cls.RWANDA_TZ)
        return local.strftime("%d %b %Y at %H:%M")
