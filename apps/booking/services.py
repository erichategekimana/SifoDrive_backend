"""
apps/booking/services.py
========================
Business logic and workflow orchestration for Driving Test Booking Concierge.
Handles application validation, district site rules, pricing resolution,
partner teacher linkage, NID encryption/audit logging, and status transitions.
"""

from datetime import date, datetime
import logging
from typing import Any, Dict, List, Optional, Union

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditAction, AuditSeverity
from apps.audit.services import AuditService
from apps.booking.models import (
    BookingApplication,
    BookingState,
    CategoryPrice,
    KicukiroWorkingSite,
    LicenseCategory,
    PartnerTeacher,
    RwandaDistrict,
)
from rest_framework.exceptions import ValidationError as ValidationException
from apps.core.exceptions import (
    BookingAlreadyProcessedException,
    BookingNotFoundException,
    ConflictException,
    InvalidBookingStateTransitionException,
    PermissionDeniedException,
    ResourceNotFoundException,
)
from apps.core.utils import PhoneNumberUtils
from apps.notifications.models import NotificationPriority
from apps.notifications.services import NotificationService

logger = logging.getLogger("apps.booking.services")


class BookingService:
    """Core domain service for handling driving test booking applications."""

    @classmethod
    @transaction.atomic
    def apply_for_booking(
        cls,
        applicant: User,
        first_name: str,
        last_name: str,
        phone_number: str,
        national_id: str,
        date_of_birth: Union[date, str],
        license_category: str,
        preferred_district: str,
        working_site: Optional[str] = None,
        partner_teacher_id: Optional[str] = None,
        request=None,
    ) -> BookingApplication:
        """
        Submit a new booking application to the system admin queue.
        Validates district site requirements, age, NID, and records category price.
        """
        # 1. Clean and normalize phone number
        normalized_phone = PhoneNumberUtils.normalize(phone_number, default_region="RW")
        if not normalized_phone:
            raise ValidationException(
                {"phone_number": f"Invalid Rwandan phone number format: {phone_number}. Enter a valid phone number (e.g. +250788123456)."}
            )

        # 2. Validate National ID format (16 digits in Rwanda)
        clean_nid = national_id.strip()
        if not (clean_nid.isdigit() and len(clean_nid) == 16):
            raise ValidationException(
                {"national_id": "National ID must be exactly 16 numeric digits."}
            )

        # 3. Parse date of birth & check minimum age (18 years)
        dob = date_of_birth
        if isinstance(dob, str):
            try:
                dob = datetime.strptime(dob, "%Y-%m-%d").date()
            except ValueError:
                raise ValidationException(
                    {"date_of_birth": "Invalid date of birth format. Use YYYY-MM-DD."}
                )

        today = date.today()
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        if age < 18:
            raise ValidationException(
                {"date_of_birth": "Applicant must be at least 18 years old to apply for a driving test."}
            )

        # 4. Validate License Category
        if license_category not in LicenseCategory.values:
            raise ValidationException(
                {"license_category": f"Allowed categories are: {list(LicenseCategory.values)}"}
            )

        # 5. Validate Preferred District
        clean_district = preferred_district.strip().upper()
        if clean_district not in RwandaDistrict.values:
            raise ValidationException(
                {"preferred_district": "Must be a recognized Rwandan district."}
            )

        # 6. Validate Kicukiro Working Site Requirement
        site_val = None
        if clean_district == RwandaDistrict.KICUKIRO:
            if not working_site:
                raise ValidationException(
                    {
                        "working_site": (
                            "For Kicukiro district, selecting a working site is required. "
                            "Choose either 'BUSANZA AUTOMATED CENTER' or 'BUSANZA SITE (KIC)'."
                        )
                    }
                )
            clean_site = working_site.strip().upper()
            valid_sites = {s.upper(): s for s in KicukiroWorkingSite.values}
            if clean_site not in valid_sites:
                raise ValidationException(
                    {"working_site": f"Must be one of: {list(KicukiroWorkingSite.values)}"}
                )
            site_val = valid_sites[clean_site]

        # 7. Validate Partner Teacher if provided
        partner_teacher = None
        if partner_teacher_id:
            try:
                partner_teacher = PartnerTeacher.objects.get(id=partner_teacher_id, is_active=True)
            except (PartnerTeacher.DoesNotExist, ValueError):
                raise ValidationException(
                    {"partner_teacher_id": "The selected partner teacher was not found or is inactive."}
                )

        # 8. Determine category price snapshot
        price_rwf = CategoryPrice.get_price_for_category(license_category)

        # 9. Instantiate and encrypt NID
        booking = BookingApplication(
            applicant=applicant,
            first_name=first_name.strip(),
            last_name=last_name.strip(),
            phone_number=normalized_phone,
            date_of_birth=dob,
            license_category=license_category,
            preferred_district=clean_district,
            working_site=site_val,
            partner_teacher=partner_teacher,
            price_rwf=price_rwf,
            state=BookingState.PENDING,
        )
        booking.set_national_id(clean_nid)
        booking.save()

        # 10. Audit Logging (Law No 058/2021)
        AuditService.log_booking_created(
            booking=booking,
            user=applicant,
            request=request,
        )
        AuditService.log_nid_write(
            writing_user=applicant,
            target_user=applicant,
            request=request,
        )

        # 11. Send Confirmation Notifications
        try:
            NotificationService.send_irembo_booking_queued(
                user=applicant,
                application_number=booking.ticket_number,
            )
        except Exception as exc:
            logger.warning("Notification dispatch failed for booking %s: %s", booking.ticket_number, exc)

        logger.info("Booking application created: %s for user %s", booking.ticket_number, applicant.id)
        return booking

    @classmethod
    @transaction.atomic
    def assign_agent(
        cls,
        booking_id: str,
        agent: User,
        request=None,
    ) -> BookingApplication:
        """Assign system admin or agent to actively process the booking."""
        try:
            booking = BookingApplication.objects.select_for_update().get(id=booking_id)
        except BookingApplication.DoesNotExist:
            raise BookingNotFoundException(f"Booking {booking_id} not found.")

        if booking.state in (BookingState.COMPLETED, BookingState.CANCELLED):
            raise InvalidBookingStateTransitionException(
                f"Cannot assign agent to booking in {booking.state} state."
            )

        booking.assigned_agent = agent
        booking.state = BookingState.PROCESSING
        booking.save(update_fields=["assigned_agent", "state", "updated_at"])

        AuditService.log_booking_locked(
            booking=booking,
            agent=agent,
            request=request,
        )
        return booking

    @classmethod
    @transaction.atomic
    def complete_booking(
        cls,
        booking_id: str,
        agent: User,
        irembo_billing_number: str,
        test_date: Optional[Union[date, str]] = None,
        test_time: Optional[Union[datetime, str]] = None,
        venue: str = "",
        confirmation_pdf=None,
        agent_notes: str = "",
        irembo_application_number: str = "",
        request=None,
    ) -> BookingApplication:
        """
        Mark booking application COMPLETED and attach the Irembo billing number.
        Sends an automated notification to the applicant with the booking results.
        """
        try:
            booking = BookingApplication.objects.select_for_update().get(id=booking_id)
        except BookingApplication.DoesNotExist:
            raise BookingNotFoundException(f"Booking {booking_id} not found.")

        if not irembo_billing_number or not irembo_billing_number.strip():
            raise ValidationException(
                {"irembo_billing_number": "Irembo billing number is required to complete the booking."}
            )

        # Parse test date if provided
        parsed_date = test_date
        if isinstance(test_date, str) and test_date.strip():
            try:
                parsed_date = datetime.strptime(test_date.strip(), "%Y-%m-%d").date()
            except ValueError:
                raise ValidationException(
                    {"confirmed_test_date": "Invalid test_date format. Use YYYY-MM-DD."}
                )

        booking.state = BookingState.COMPLETED
        booking.irembo_billing_number = irembo_billing_number.strip()
        if irembo_application_number:
            booking.irembo_application_number = irembo_application_number.strip()
        if parsed_date:
            booking.confirmed_test_date = parsed_date
        if test_time:
            booking.confirmed_test_time = test_time
        if venue:
            booking.confirmed_venue = venue.strip()
        if confirmation_pdf:
            booking.confirmation_pdf = confirmation_pdf
        if agent_notes:
            booking.agent_notes = agent_notes.strip()
        booking.completed_at = timezone.now()
        booking.save()

        # Audit Logging
        AuditService.log_booking_confirmed(
            booking=booking,
            agent=agent,
            application_number=booking.irembo_billing_number,
            request=request,
        )

        # Dispatch confirmation notification (SMS + In-App)
        test_date_str = str(booking.confirmed_test_date) if booking.confirmed_test_date else "To be announced"
        venue_str = booking.confirmed_venue or booking.working_site or booking.preferred_district
        try:
            NotificationService.send_irembo_booking_confirmed(
                user=booking.applicant,
                test_date=test_date_str,
                test_center=venue_str,
                irembo_ref=booking.irembo_billing_number,
            )
        except Exception as exc:
            logger.warning("Failed to send completion notification for %s: %s", booking.ticket_number, exc)

        logger.info("Booking %s marked COMPLETED by agent %s", booking.ticket_number, agent.id)
        return booking

    @classmethod
    @transaction.atomic
    def mark_slots_unavailable(
        cls,
        booking_id: str,
        agent: User,
        agent_notes: str = "",
        request=None,
    ) -> BookingApplication:
        """Mark booking as slots unavailable while retaining applicant in the automated queue."""
        try:
            booking = BookingApplication.objects.select_for_update().get(id=booking_id)
        except BookingApplication.DoesNotExist:
            raise BookingNotFoundException(f"Booking {booking_id} not found.")

        old_state = booking.state
        booking.state = BookingState.SLOTS_UNAVAILABLE
        if agent_notes:
            booking.agent_notes = agent_notes.strip()
        booking.save(update_fields=["state", "agent_notes", "updated_at"])

        AuditService.log_booking_state_changed(
            booking=booking,
            from_state=old_state,
            to_state=BookingState.SLOTS_UNAVAILABLE,
            performed_by=agent,
            reason=agent_notes or "Slots currently unavailable on Irembo",
            request=request,
        )

        try:
            NotificationService.send_notification(
                recipient=booking.applicant,
                notification_type="BOOKING_SLOTS_EXHAUSTED",
                channel="SMS",
                priority=NotificationPriority.NORMAL,
                context={"ticket_number": booking.ticket_number},
            )
        except Exception as exc:
            logger.warning("Failed to dispatch slots exhausted alert: %s", exc)

        return booking

    @classmethod
    @transaction.atomic
    def cancel_booking(
        cls,
        booking_id: str,
        user: User,
        reason: str = "",
        request=None,
    ) -> BookingApplication:
        """Cancel a pending or processing booking application."""
        try:
            booking = BookingApplication.objects.select_for_update().get(id=booking_id)
        except BookingApplication.DoesNotExist:
            raise BookingNotFoundException(f"Booking {booking_id} not found.")

        # Applicants can only cancel their own pending bookings; staff can cancel any
        if not user.is_staff and booking.applicant != user:
            raise PermissionDeniedException("You cannot cancel another applicant's booking.")

        if booking.state == BookingState.COMPLETED:
            raise InvalidBookingStateTransitionException("Cannot cancel a completed booking.")

        old_state = booking.state
        booking.state = BookingState.CANCELLED
        if reason:
            booking.agent_notes = f"[Cancellation Reason]: {reason}"
        booking.save(update_fields=["state", "agent_notes", "updated_at"])

        AuditService.log_booking_state_changed(
            booking=booking,
            from_state=old_state,
            to_state=BookingState.CANCELLED,
            performed_by=user,
            reason=reason or "Booking cancelled",
            request=request,
        )
        return booking

    @classmethod
    def get_decrypted_national_id(
        cls,
        booking: BookingApplication,
        requesting_user: User,
        request=None,
    ) -> Optional[str]:
        """
        Securely decrypt National ID for authorized administrators or the applicant themselves.
        Mandatory audit logging compliant with Rwanda Law No 058/2021.
        """
        is_owner = booking.applicant == requesting_user
        is_admin = requesting_user.is_staff or getattr(requesting_user, "role", None) in (
            "SYSTEM_ADMIN", "ENTERPRISE_ADMIN", "BOARD_REVIEWER"
        )

        if not (is_owner or is_admin):
            raise PermissionDeniedException("Unauthorized to access applicant National ID.")

        nid = booking.get_decrypted_national_id()

        # Audit log citizen PII access
        AuditService.log_nid_access(
            actor=requesting_user,
            target_user=booking.applicant,
            purpose=f"View National ID for booking {booking.ticket_number}",
            request=request,
        )
        return nid


class PartnerTeacherService:
    """Service for managing driving teacher partners."""

    @classmethod
    def get_active_teachers(cls) -> List[PartnerTeacher]:
        return list(PartnerTeacher.objects.filter(is_active=True).order_by("first_name", "last_name"))

    @classmethod
    def create_teacher(
        cls,
        first_name: str,
        last_name: str,
        phone_number: str,
        driving_school_affiliation: str = "",
        notes: str = "",
    ) -> PartnerTeacher:
        clean_phone = PhoneNumberUtils.normalize(phone_number, default_region="RW") or phone_number.strip()
        return PartnerTeacher.objects.create(
            first_name=first_name.strip(),
            last_name=last_name.strip(),
            phone_number=clean_phone,
            driving_school_affiliation=driving_school_affiliation.strip(),
            notes=notes.strip(),
            is_active=True,
        )


class CategoryPriceService:
    """Service for setting and retrieving booking prices per category."""

    @classmethod
    def get_all_prices(cls) -> List[CategoryPrice]:
        return list(CategoryPrice.objects.all().order_by("category"))

    @classmethod
    def set_price(
        cls,
        category: str,
        price_rwf: int,
        description: str = "",
        is_active: bool = True,
    ) -> CategoryPrice:
        if category not in LicenseCategory.values:
            raise ValidationException(f"Invalid category: {category}")
        if price_rwf < 0:
            raise ValidationException("Price cannot be negative.")

        obj, _ = CategoryPrice.objects.update_or_create(
            category=category,
            defaults={
                "price_rwf": price_rwf,
                "description": description.strip(),
                "is_active": is_active,
            }
        )
        return obj
