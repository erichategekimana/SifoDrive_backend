from datetime import datetime
import logging
from typing import Any, Dict, List, Optional

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

from apps.accounts.models import User
from apps.live_classes.models import (
    AttendanceStatus,
    ClassAttendance,
    LiveClass,
    LiveClassStatus,
)

logger = logging.getLogger("apps.live_classes.services")


class AttendanceService:
    """
    Business service for recording and calculating student live class attendance.
    Directly feeds the 75% attendance threshold requirement for provisional driving mock exam eligibility.
    """

    ELIGIBILITY_THRESHOLD = 0.75  # 75% required attendance

    @classmethod
    @transaction.atomic
    def record_attendance(
        cls,
        live_class: LiveClass,
        student: User,
        status: str = AttendanceStatus.PRESENT,
        joined_at: Optional[datetime] = None,
        minutes_attended: int = 0,
        marked_by: Optional[User] = None,
        notes: str = "",
    ) -> ClassAttendance:
        """Record or update a student's attendance record for a specific class."""
        if status not in AttendanceStatus.values:
            raise ValidationError(f"Invalid attendance status: {status}")

        attendance, created = ClassAttendance.objects.update_or_create(
            live_class=live_class,
            student=student,
            defaults={
                "status": status,
                "joined_at": joined_at,
                "minutes_attended": minutes_attended,
                "marked_by": marked_by,
                "notes": notes.strip(),
            },
        )
        logger.info(
            "Attendance %s: student=%s, class=%s, status=%s",
            "created" if created else "updated",
            student.phone_number,
            live_class.id,
            status,
        )
        return attendance

    @classmethod
    @transaction.atomic
    def batch_record_attendance(
        cls,
        live_class: LiveClass,
        records: List[Dict[str, Any]],
        marked_by: Optional[User] = None,
    ) -> int:
        """
        Batch update/create attendance records for an entire cohort session.
        records: list of dicts with keys:
          - student_id (UUID or User object)
          - status (PRESENT, LATE, ABSENT, EXCUSED, WATCHED_RECORDING)
          - minutes_attended (optional int)
          - notes (optional str)
          - joined_at (optional datetime)
        """
        updated_count = 0
        for item in records:
            student_id = item.get("student_id")
            if not student_id:
                continue

            try:
                student = User.objects.get(id=student_id)
            except User.DoesNotExist:
                logger.warning("Student %s not found for attendance batch", student_id)
                continue

            cls.record_attendance(
                live_class=live_class,
                student=student,
                status=item.get("status", AttendanceStatus.PRESENT),
                joined_at=item.get("joined_at"),
                minutes_attended=item.get("minutes_attended", 0),
                marked_by=marked_by,
                notes=item.get("notes", ""),
            )
            updated_count += 1

        logger.info("Batch recorded %d attendance records for class %s", updated_count, live_class.id)
        return updated_count

    @classmethod
    def get_attendance_rate(cls, student: User) -> float:
        """
        Return live class attendance rate as a float between 0.0 and 1.0.
        Used by the Examination Eligibility Engine to enforce the 75% requirement.

        Eligibility logic:
          - If student has no absence and no late records in roll call attendance, return 1.0 (100%).
          - If recorded attendance sessions exist for the student, compute rate based on present, late, and absent.
          - If total mandatory classes is 0, return 1.0 (student is not penalized before classes begin).
        """
        attendances = ClassAttendance.objects.filter(student=student)
        absent_count = attendances.filter(status=AttendanceStatus.ABSENT).count()
        late_count = attendances.filter(status=AttendanceStatus.LATE).count()
        present_count = attendances.filter(
            status__in=[AttendanceStatus.PRESENT, AttendanceStatus.EXCUSED]
        ).count()

        # If student has no absence and no late, they have 100% attendance
        if absent_count == 0 and late_count == 0:
            return 1.0

        total_marked = present_count + late_count + absent_count
        if total_marked > 0:
            attended_weight = present_count + (late_count * 0.8)
            rate = round(attended_weight / total_marked, 4)
            return min(max(rate, 0.0), 1.0)

        enrolled_cohort_ids = list(
            student.enrolled_cohorts.filter(is_active=True).values_list("id", flat=True)
        )

        class_filter = Q(status__in=[LiveClassStatus.COMPLETED, LiveClassStatus.IN_PROGRESS])

        if enrolled_cohort_ids:
            class_filter &= Q(cohort_id__in=enrolled_cohort_ids) | Q(cohort__isnull=True, is_published=True)
        else:
            class_filter &= Q(is_published=True)

        total_classes = LiveClass.objects.filter(class_filter).count()

        if total_classes == 0:
            return 1.0

        attended_count = ClassAttendance.objects.filter(
            student=student,
            live_class__in=LiveClass.objects.filter(class_filter),
            status__in=[
                AttendanceStatus.PRESENT,
                AttendanceStatus.LATE,
                AttendanceStatus.EXCUSED,
            ],
        ).count()

        rate = round(attended_count / total_classes, 4)
        return min(rate, 1.0)

    @classmethod
    def get_student_attendance_summary(cls, student: User, for_student_view: bool = False) -> Dict[str, Any]:
        """
        Return comprehensive attendance report for student dashboard & exam gate verification.
        - EXCUSED weighs the same as PRESENT towards attendance rate and exam eligibility.
        - On student dashboard: only 3 statuses are displayed (present, late, absent),
          with EXCUSED weighted and counted as PRESENT.
        - For tutors/admins: full breakdown including excused.
        """
        attendances = ClassAttendance.objects.filter(student=student)
        raw_present_count = attendances.filter(status=AttendanceStatus.PRESENT).count()
        late_count = attendances.filter(status=AttendanceStatus.LATE).count()
        absent_count = attendances.filter(status=AttendanceStatus.ABSENT).count()
        excused_count = attendances.filter(status=AttendanceStatus.EXCUSED).count()

        total_attended = raw_present_count + excused_count + late_count

        rate = cls.get_attendance_rate(student)
        # Verify 100% if no absence and no late
        if absent_count == 0 and late_count == 0:
            rate = 1.0
            percentage = 100.0
        else:
            percentage = round(rate * 100, 1)

        if for_student_view:
            return {
                "rate": rate,
                "percentage": percentage,
                "attendance_rate": rate,
                "is_eligible_for_exam": rate >= cls.ELIGIBILITY_THRESHOLD,
                "threshold_required_percentage": cls.ELIGIBILITY_THRESHOLD * 100,
                "present_count": raw_present_count + excused_count,  # Excused weighs the same as Present for students
                "late_count": late_count,
                "absent_count": absent_count,
                "total_attended": total_attended,
            }

        return {
            "rate": rate,
            "percentage": percentage,
            "attendance_rate": rate,
            "is_eligible_for_exam": rate >= cls.ELIGIBILITY_THRESHOLD,
            "threshold_required_percentage": cls.ELIGIBILITY_THRESHOLD * 100,
            "present_count": raw_present_count,
            "late_count": late_count,
            "absent_count": absent_count,
            "excused_count": excused_count,
            "total_attended": total_attended,
        }
