import logging
from django.contrib.auth import get_user_model
from apps.accounts.constants import AccountStatus, UserRole
from apps.accounts.models import EnterpriseProfile, StudentProfile

User = get_user_model()
logger = logging.getLogger(__name__)


class EnterpriseService:
    """Service layer for Driving School (ENTERPRISE_ADMIN) operations."""

    @classmethod
    def get_or_create_profile(cls, user: User) -> EnterpriseProfile:
        """Retrieve or initialize an EnterpriseProfile for an enterprise user."""
        if user.role != UserRole.ENTERPRISE_ADMIN:
            raise ValueError("Only users with role ENTERPRISE_ADMIN can have an EnterpriseProfile.")

        school_name = user.school_name or f"Driving School {str(user.id)[:6].upper()}"
        reg_number = f"RDB-DS-{str(user.id)[:8].upper()}"
        
        profile, created = EnterpriseProfile.objects.get_or_create(
            user=user,
            defaults={
                "school_name": school_name,
                "registration_number": reg_number,
                "concurrent_station_quota": user.station_quota or 20,
            },
        )
        return profile

    @classmethod
    def get_enterprise_dashboard_stats(cls, user: User) -> dict:
        """Aggregate lab utilization and student enrollment metrics."""
        profile = cls.get_or_create_profile(user)
        
        # Check active exam sessions for enterprise driving school
        active_exam_sessions = 0
        try:
            from apps.examinations.models import ExamSession
            active_exam_sessions = ExamSession.objects.filter(
                user__school_name=profile.school_name,
                status="IN_PROGRESS",
            ).count()
        except Exception:
            active_exam_sessions = 0

        quota = profile.concurrent_station_quota
        available_seats = max(0, quota - active_exam_sessions)
        utilization_rate = round((active_exam_sessions / quota * 100), 1) if quota > 0 else 0

        # Enrolled school students count
        total_students = User.objects.filter(
            role=UserRole.STUDENT,
            school_name=profile.school_name,
        ).count()

        return {
            "school_name": profile.school_name,
            "registration_number": profile.registration_number,
            "district": profile.district,
            "sector": profile.sector,
            "address_line": profile.address_line,
            "contact_email": profile.contact_email,
            "contact_phone": profile.contact_phone,
            "concurrent_station_quota": quota,
            "active_exam_sessions": active_exam_sessions,
            "available_workstations": available_seats,
            "utilization_percentage": utilization_rate,
            "total_students": total_students,
            "is_verified": profile.is_verified_school,
        }

    @classmethod
    def get_school_students(cls, user: User) -> list[dict]:
        """List students enrolled under this driving school."""
        profile = cls.get_or_create_profile(user)
        students = User.objects.filter(
            role=UserRole.STUDENT,
            school_name=profile.school_name,
        ).select_related("student_profile").order_by("-created_at")

        return [
            {
                "id": str(s.id),
                "full_name": s.full_name,
                "phone_number": s.phone_number,
                "student_id": s.student_id,
                "status": s.status,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in students
        ]

    @classmethod
    def bulk_enroll_students(cls, enterprise_user: User, students_data: list[dict]) -> dict:
        """
        Batch register students under this driving school.
        Accepts a list of dicts with phone_number, first_name, last_name, etc.
        """
        profile = cls.get_or_create_profile(enterprise_user)
        created_count = 0
        skipped_count = 0
        errors = []

        for item in students_data:
            phone = item.get("phone_number", "").strip()
            first_name = item.get("first_name", "").strip()
            last_name = item.get("last_name", "").strip()

            if not phone or not first_name or not last_name:
                skipped_count += 1
                errors.append(f"Missing required fields for student: {phone or 'Unknown'}")
                continue

            if User.objects.filter(phone_number=phone).exists():
                skipped_count += 1
                errors.append(f"Phone number {phone} is already registered.")
                continue

            try:
                new_student = User.objects.create_user(
                    phone_number=phone,
                    first_name=first_name,
                    last_name=last_name,
                    role=UserRole.STUDENT,
                    status=AccountStatus.ACTIVE,
                    school_name=profile.school_name,
                )
                new_student.terms_of_service_accepted = True
                new_student.privacy_policy_accepted = True
                new_student.save(update_fields=["terms_of_service_accepted", "privacy_policy_accepted"])

                license_cat = item.get("license_category", "B")
                StudentProfile.objects.create(
                    user=new_student,
                    license_category=license_cat,
                )
                created_count += 1
            except Exception as e:
                skipped_count += 1
                errors.append(f"Failed to create {phone}: {str(e)}")

        return {
            "created_count": created_count,
            "skipped_count": skipped_count,
            "errors": errors,
        }

    @classmethod
    def update_enterprise_profile(cls, user: User, validated_data: dict) -> EnterpriseProfile:
        """Update driving school details."""
        profile = cls.get_or_create_profile(user)
        for key, val in validated_data.items():
            if hasattr(profile, key):
                setattr(profile, key, val)
        profile.save()
        return profile
