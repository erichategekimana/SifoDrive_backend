from typing import List
from apps.booking.models import PartnerTeacher
from apps.core.utils import PhoneNumberUtils


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
