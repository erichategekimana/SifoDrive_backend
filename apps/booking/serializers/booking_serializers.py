from datetime import date
from rest_framework import serializers

from apps.booking.models import (
    BookingApplication,
    BookingState,
    KicukiroWorkingSite,
    LicenseCategory,
    RwandaDistrict,
)
from apps.core.utils import PhoneNumberUtils
from .partner_teacher_serializers import PartnerTeacherDropdownSerializer


class BookingApplicationCreateSerializer(serializers.Serializer):
    """Validation serializer for user driving test booking submission."""

    first_name = serializers.CharField(max_length=100)
    last_name = serializers.CharField(max_length=100)
    phone_number = serializers.CharField(max_length=25)
    national_id = serializers.CharField(max_length=16, min_length=16)
    date_of_birth = serializers.DateField()
    license_category = serializers.ChoiceField(choices=LicenseCategory.choices)
    preferred_district = serializers.ChoiceField(choices=RwandaDistrict.choices)
    working_site = serializers.ChoiceField(
        choices=KicukiroWorkingSite.choices,
        required=False,
        allow_null=True,
        allow_blank=True,
    )
    partner_teacher_id = serializers.UUIDField(required=False, allow_null=True)

    def validate_national_id(self, value):
        cleaned = value.strip()
        if not (cleaned.isdigit() and len(cleaned) == 16):
            raise serializers.ValidationError("Rwandan National ID must be exactly 16 numeric digits.")
        return cleaned

    def validate_phone_number(self, value):
        normalized = PhoneNumberUtils.normalize(value, default_region="RW")
        if not normalized:
            raise serializers.ValidationError("Enter a valid Rwandan phone number (e.g. +250788123456).")
        return normalized

    def validate_date_of_birth(self, value):
        today = date.today()
        age = today.year - value.year - ((today.month, today.day) < (value.month, value.day))
        if age < 18:
            raise serializers.ValidationError("Applicant must be at least 18 years old to apply.")
        return value

    def validate(self, attrs):
        district = attrs.get("preferred_district", "").upper()
        site = attrs.get("working_site")

        # Specific business rule: If Kicukiro, working_site is mandatory
        if district == RwandaDistrict.KICUKIRO:
            if not site:
                raise serializers.ValidationError({
                    "working_site": (
                        "For Kicukiro district, selecting a working site is required. "
                        "Choose either 'BUSANZA AUTOMATED CENTER' or 'BUSANZA SITE (KIC)'."
                    )
                })
            if site not in KicukiroWorkingSite.values:
                raise serializers.ValidationError({
                    "working_site": f"Invalid site for Kicukiro. Must be one of: {list(KicukiroWorkingSite.values)}"
                })
        else:
            attrs["working_site"] = None

        return attrs


class BookingApplicationListSerializer(serializers.ModelSerializer):
    """Summary list serializer for user inbox and admin queues."""

    full_name = serializers.CharField(read_only=True)
    partner_teacher_name = serializers.SerializerMethodField()
    phone_masked = serializers.SerializerMethodField()

    class Meta:
        model = BookingApplication
        fields = [
            "id",
            "ticket_number",
            "first_name",
            "last_name",
            "full_name",
            "phone_number",
            "phone_masked",
            "license_category",
            "preferred_district",
            "working_site",
            "price_rwf",
            "state",
            "partner_teacher_name",
            "irembo_billing_number",
            "confirmed_test_date",
            "confirmed_venue",
            "submitted_at",
            "completed_at",
        ]
        read_only_fields = fields

    def get_partner_teacher_name(self, obj: BookingApplication):
        return obj.partner_teacher.full_name if obj.partner_teacher else None

    def get_phone_masked(self, obj: BookingApplication):
        return PhoneNumberUtils.obfuscate(obj.phone_number)


class BookingApplicationDetailSerializer(serializers.ModelSerializer):
    """Comprehensive detail serializer for a single booking application."""

    full_name = serializers.CharField(read_only=True)
    partner_teacher = PartnerTeacherDropdownSerializer(read_only=True)
    assigned_agent_name = serializers.SerializerMethodField()
    decrypted_national_id = serializers.SerializerMethodField()

    class Meta:
        model = BookingApplication
        fields = [
            "id",
            "ticket_number",
            "applicant",
            "first_name",
            "last_name",
            "full_name",
            "phone_number",
            "date_of_birth",
            "decrypted_national_id",
            "license_category",
            "preferred_district",
            "working_site",
            "price_rwf",
            "partner_teacher",
            "state",
            "assigned_agent",
            "assigned_agent_name",
            "irembo_billing_number",
            "irembo_application_number",
            "confirmed_test_date",
            "confirmed_test_time",
            "confirmed_venue",
            "confirmation_pdf",
            "agent_notes",
            "submitted_at",
            "completed_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_assigned_agent_name(self, obj: BookingApplication):
        if obj.assigned_agent:
            return obj.assigned_agent.get_full_name() or obj.assigned_agent.phone_number
        return None

    def get_decrypted_national_id(self, obj: BookingApplication):
        request = self.context.get("request")
        if not request or not request.user or not request.user.is_authenticated:
            return None

        # Decrypt only for admin or applicant themselves
        is_owner = obj.applicant == request.user
        is_staff = request.user.is_staff or getattr(request.user, "role", None) in (
            "SYSTEM_ADMIN", "ENTERPRISE_ADMIN", "BOARD_REVIEWER"
        )
        if is_owner or is_staff:
            return obj.get_decrypted_national_id()
        return None


class AdminBookingStatusUpdateSerializer(serializers.Serializer):
    """Payload validation for changing booking status."""

    state = serializers.ChoiceField(choices=BookingState.choices)
    agent_notes = serializers.CharField(required=False, allow_blank=True)


class AdminBookingCompleteSerializer(serializers.Serializer):
    """Payload validation for completing a booking and attaching Irembo billing number."""

    irembo_billing_number = serializers.CharField(max_length=100)
    irembo_application_number = serializers.CharField(max_length=100, required=False, allow_blank=True)
    confirmed_test_date = serializers.DateField(required=False, allow_null=True)
    confirmed_test_time = serializers.TimeField(required=False, allow_null=True)
    confirmed_venue = serializers.CharField(max_length=255, required=False, allow_blank=True)
    confirmation_pdf = serializers.FileField(required=False, allow_null=True)
    agent_notes = serializers.CharField(required=False, allow_blank=True)
