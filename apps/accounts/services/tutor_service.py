import logging
from django.contrib.auth import get_user_model
from apps.accounts.constants import UserRole
from apps.accounts.models import TutorProfile

User = get_user_model()
logger = logging.getLogger(__name__)


class TutorService:
    """Service layer for Tutor and Theoretical Facilitator operations."""

    @classmethod
    def get_or_create_profile(cls, user: User) -> TutorProfile:
        """Retrieve or initialize a TutorProfile for a user with role=TUTOR."""
        if user.role != UserRole.TUTOR:
            raise ValueError("Only users with role TUTOR can have a TutorProfile.")
        
        tutor_code = f"SIFO-TUT-{str(user.id)[:6].upper()}"
        profile, created = TutorProfile.objects.get_or_create(
            user=user,
            defaults={
                "tutor_code": tutor_code,
                "title": "Theory & Practical Driving Instructor",
            },
        )
        return profile

    @classmethod
    def get_tutor_dashboard_stats(cls, user: User) -> dict:
        """
        Aggregate instructor overview metrics:
          - Assigned learners count
          - Cohorts supervised
          - Active Google Meet session status
          - Average student progress rate
        """
        profile = cls.get_or_create_profile(user)
        assigned_students_qs = user.tutoring_students.all().select_related("student_profile")
        total_students = assigned_students_qs.count()
        active_students = assigned_students_qs.filter(is_active=True).count()

        return {
            "tutor_code": profile.tutor_code,
            "title": profile.title,
            "bio": profile.bio,
            "specialization_categories": profile.specialization_categories,
            "default_meeting_url": profile.default_meeting_url,
            "is_available": profile.is_available_for_tutoring,
            "max_capacity": profile.max_student_capacity,
            "total_students": total_students,
            "active_students": active_students,
            "rating": float(profile.rating),
            "teaching_hours": profile.total_teaching_hours,
        }

    @classmethod
    def get_assigned_students(cls, user: User) -> list[dict]:
        """Fetch list of students supervised by this tutor with learning progress details."""
        from apps.accounts.services.student_service import StudentService

        students = user.tutoring_students.all().select_related("student_profile").order_by("-created_at")
        results = []
        for s in students:
            profile = getattr(s, "student_profile", None)
            eligibility = StudentService.check_exam_eligibility(s)
            results.append({
                "id": str(s.id),
                "full_name": s.full_name,
                "phone_number": s.phone_number,
                "student_id": s.student_id,
                "status": s.status,
                "license_category": profile.license_category if profile else "B",
                "current_streak_days": profile.current_streak_days if profile else 0,
                "exam_eligible": eligibility.get("eligible", False),
                "attendance_rate": eligibility.get("criteria", {}).get("attendance_rate", 0),
                "module_completion": eligibility.get("criteria", {}).get("module_completion", 0),
            })
        return results

    @classmethod
    def update_tutor_profile(cls, user: User, validated_data: dict) -> TutorProfile:
        """Update instructor details."""
        profile = cls.get_or_create_profile(user)
        for key, val in validated_data.items():
            if hasattr(profile, key):
                setattr(profile, key, val)
        profile.save()
        return profile
