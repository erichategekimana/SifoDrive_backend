"""
apps/live_classes/services.py
=============================
Domain business services for Live Classes, Cohorts, and Attendance Tracking.
Encapsulates all business logic, validation, transaction boundaries,
and notification dispatching.
"""

from datetime import date, datetime, time
import logging
from typing import Any, Dict, List, Optional, Tuple, Union

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Q, QuerySet
from django.utils import timezone

from apps.accounts.constants import UserRole
from apps.accounts.models import User
from apps.notifications.services import NotificationService
from .models import (
    AttendanceStatus,
    ClassAttendance,
    ClassResource,
    Cohort,
    LiveClass,
    LiveClassStatus,
)

logger = logging.getLogger("apps.live_classes.services")


# ===========================================================================
# Cohort Service
# ===========================================================================

class CohortService:
    """
    Business service managing student batches / cohorts, tutor assignments,
    and capacity constraints.
    """

    @classmethod
    @transaction.atomic
    def create_cohort(
        cls,
        name: str,
        code: str,
        start_date: date,
        end_date: Optional[date] = None,
        max_capacity: int = 50,
        schedule_description: str = "",
        description: str = "",
        assigned_tutors: Optional[List[User]] = None,
        students: Optional[List[User]] = None,
    ) -> Cohort:
        """Create a new cohort and optionally assign initial tutors and students."""
        code = code.strip().upper()
        if Cohort.objects.filter(code=code).exists():
            raise ValidationError(f"Cohort with code '{code}' already exists.")

        if end_date and end_date < start_date:
            raise ValidationError("End date cannot precede start date.")

        cohort = Cohort.objects.create(
            name=name.strip(),
            code=code,
            start_date=start_date,
            end_date=end_date,
            max_capacity=max_capacity,
            schedule_description=schedule_description.strip(),
            description=description.strip(),
        )

        if assigned_tutors:
            cls.assign_tutors(cohort, [t.id for t in assigned_tutors])
        if students:
            cls.enroll_students(cohort, [s.id for s in students])

        logger.info("Cohort created: %s (code=%s)", cohort.name, cohort.code)
        return cohort

    @classmethod
    @transaction.atomic
    def enroll_students(cls, cohort: Cohort, student_ids: List[Union[str, int]]) -> Tuple[int, List[str]]:
        """
        Enroll a list of students into the cohort, respecting max capacity.
        Returns (count_enrolled, warnings).
        """
        students = User.objects.filter(id__in=student_ids, role=UserRole.STUDENT, is_active=True)
        current_count = cohort.students.count()
        incoming_count = students.count()
        warnings = []

        if current_count + incoming_count > cohort.max_capacity:
            warnings.append(
                f"Enrolling {incoming_count} students will exceed maximum capacity ({cohort.max_capacity})."
            )

        cohort.students.add(*students)
        logger.info(
            "Enrolled %d students into cohort %s (total: %d)",
            incoming_count,
            cohort.code,
            cohort.students.count(),
        )
        return incoming_count, warnings

    @classmethod
    @transaction.atomic
    def unenroll_students(cls, cohort: Cohort, student_ids: List[Union[str, int]]) -> int:
        """Remove students from a cohort."""
        students = User.objects.filter(id__in=student_ids)
        cohort.students.remove(*students)
        count = len(student_ids)
        logger.info("Removed %d students from cohort %s", count, cohort.code)
        return count

    @classmethod
    @transaction.atomic
    def assign_tutors(cls, cohort: Cohort, tutor_ids: List[Union[str, int]]) -> int:
        """Assign tutors to manage and teach this cohort."""
        tutors = User.objects.filter(
            id__in=tutor_ids,
            role__in=[UserRole.TUTOR, UserRole.TRAINING_ADMIN, UserRole.SYSTEM_ADMIN],
            is_active=True,
        )
        cohort.assigned_tutors.add(*tutors)
        count = tutors.count()
        logger.info("Assigned %d tutors to cohort %s", count, cohort.code)
        return count

    @classmethod
    @transaction.atomic
    def unassign_tutors(cls, cohort: Cohort, tutor_ids: List[Union[str, int]]) -> int:
        """Remove tutor assignment from this cohort."""
        tutors = User.objects.filter(id__in=tutor_ids)
        cohort.assigned_tutors.remove(*tutors)
        count = len(tutor_ids)
        logger.info("Unassigned %d tutors from cohort %s", count, cohort.code)
        return count

    @classmethod
    def get_student_cohorts(cls, user: User) -> QuerySet:
        """Return all active cohorts a student is currently enrolled in."""
        return user.enrolled_cohorts.filter(is_active=True)

    @classmethod
    def get_tutor_cohorts(cls, user: User) -> QuerySet:
        """Return all active cohorts assigned to this tutor."""
        return user.assigned_cohorts.filter(is_active=True)


# ===========================================================================
# Live Class Service
# ===========================================================================

class LiveClassService:
    """
    Business service managing live class scheduling, Google Meet integration,
    session lifecycle (scheduled -> in progress -> completed), and reminders.
    """

    @classmethod
    @transaction.atomic
    def schedule_class(
        cls,
        title: str,
        scheduled_date: date,
        start_time: time,
        end_time: time,
        google_meet_url: str,
        topic: str = "",
        cohort: Optional[Cohort] = None,
        tutor: Optional[User] = None,
        module=None,
        lesson=None,
        notes: str = "",
        is_published: bool = True,
        created_by: Optional[User] = None,
    ) -> LiveClass:
        """
        Schedule a new live class session.
        Validates schedule boundaries and dispatches scheduled notifications.
        """
        if start_time >= end_time:
            raise ValidationError("Start time must be strictly before end time.")

        if tutor and tutor.role not in [UserRole.TUTOR, UserRole.TRAINING_ADMIN, UserRole.SYSTEM_ADMIN]:
            raise ValidationError("Assigned user must have Tutor or Admin role.")

        live_class = LiveClass.objects.create(
            title=title.strip(),
            topic=topic.strip(),
            cohort=cohort,
            tutor=tutor,
            module=module,
            lesson=lesson,
            scheduled_date=scheduled_date,
            start_time=start_time,
            end_time=end_time,
            google_meet_url=google_meet_url.strip(),
            status=LiveClassStatus.SCHEDULED,
            is_published=is_published,
            notes=notes.strip(),
            created_by=created_by,
        )

        logger.info(
            "Live class scheduled: '%s' on %s (%s - %s), tutor=%s, cohort=%s",
            live_class.title,
            scheduled_date,
            start_time,
            end_time,
            tutor.phone_number if tutor else "Unassigned",
            cohort.code if cohort else "Open",
        )

        if is_published:
            cls.notify_students_scheduled(live_class)

        return live_class

    @classmethod
    @transaction.atomic
    def schedule_recurring_classes(
        cls,
        title: str,
        start_date: date,
        day_of_week: int,
        start_time: time,
        end_time: time,
        period_months: int = 3,
        google_meet_url: str = "",
        cohort: Optional[Cohort] = None,
        tutor: Optional[User] = None,
        topic: str = "",
        is_published: bool = True,
        notes: str = "",
        created_by: Optional[User] = None,
    ) -> List[LiveClass]:
        """
        Schedule recurring live classes for a specific day of the week over a given period in months.
        E.g. each Tuesday 2pm for 3 months.
        """
        import calendar
        from datetime import timedelta

        if start_time >= end_time:
            raise ValidationError("Start time must be strictly before end time.")

        # Calculate approximate end date based on period_months
        year = start_date.year
        month = start_date.month + period_months
        while month > 12:
            year += 1
            month -= 12
        max_day = calendar.monthrange(year, month)[1]
        day = min(start_date.day, max_day)
        period_end_date = date(year, month, day)

        # Advance to first occurrence of day_of_week
        cur = start_date
        days_ahead = (day_of_week - cur.weekday()) % 7
        cur = cur + timedelta(days=days_ahead)

        if not google_meet_url:
            meet_slug = f"sifo-{title.lower()[:8].strip().replace(' ', '-')}-{calendar.day_abbr[day_of_week].lower()}"
            google_meet_url = f"https://meet.google.com/{meet_slug}"

        created_sessions = []
        while cur <= period_end_date:
            session = LiveClass.objects.create(
                title=title.strip(),
                topic=topic.strip(),
                cohort=cohort,
                tutor=tutor,
                scheduled_date=cur,
                start_time=start_time,
                end_time=end_time,
                google_meet_url=google_meet_url.strip(),
                status=LiveClassStatus.SCHEDULED,
                is_published=is_published,
                notes=notes.strip(),
                created_by=created_by,
            )
            created_sessions.append(session)
            cur += timedelta(days=7)

        logger.info(
            "Scheduled %d recurring classes for '%s' (Day %d, %d months)",
            len(created_sessions),
            title,
            day_of_week,
            period_months,
        )
        return created_sessions

    @classmethod
    @transaction.atomic
    def reschedule_class(
        cls,
        live_class: LiveClass,
        new_date: date,
        new_start_time: time,
        new_end_time: time,
        reason: str = "",
    ) -> LiveClass:
        """Reschedule date/time for an upcoming class and notify enrolled students."""
        if new_start_time >= new_end_time:
            raise ValidationError("Start time must precede end time.")

        if live_class.status == LiveClassStatus.COMPLETED:
            raise ValidationError("Cannot reschedule a session that has already completed.")

        live_class.scheduled_date = new_date
        live_class.start_time = new_start_time
        live_class.end_time = new_end_time
        live_class.status = LiveClassStatus.RESCHEDULED
        if reason:
            prefix = f"\n[Rescheduled: {reason}]"
            live_class.notes = (live_class.notes + prefix).strip()
        live_class.save()

        logger.info("Live class %s rescheduled to %s %s", live_class.id, new_date, new_start_time)
        cls.notify_students_scheduled(live_class, is_reschedule=True)
        return live_class

    @classmethod
    @transaction.atomic
    def start_session(cls, live_class: LiveClass, tutor: Optional[User] = None) -> LiveClass:
        """
        Transition session to IN_PROGRESS when tutor joins/starts the session.
        Can send SMS reminder with Meet link to students starting right now.
        """
        if live_class.status == LiveClassStatus.COMPLETED:
            raise ValidationError("This class has already ended.")

        live_class.start_session()
        logger.info("Live session started: %s (id=%s)", live_class.title, live_class.id)

        # Dispatch immediate SMS reminder with meet link
        cls.notify_students_reminder(live_class)
        return live_class

    @classmethod
    @transaction.atomic
    def end_session(
        cls,
        live_class: LiveClass,
        recording_url: str = "",
        tutor: Optional[User] = None,
    ) -> LiveClass:
        """Mark session as COMPLETED and save recording URL if available."""
        live_class.end_session(recording_url=recording_url)
        logger.info("Live session ended: %s (recording=%s)", live_class.title, bool(recording_url))
        return live_class

    @classmethod
    @transaction.atomic
    def cancel_class(cls, live_class: LiveClass, reason: str = "") -> LiveClass:
        """Cancel a scheduled class."""
        if live_class.status == LiveClassStatus.COMPLETED:
            raise ValidationError("Cannot cancel an already completed session.")

        live_class.status = LiveClassStatus.CANCELLED
        if reason:
            live_class.notes = (live_class.notes + f"\n[Cancelled: {reason}]").strip()
        live_class.save(update_fields=["status", "notes", "updated_at"])
        logger.info("Live class cancelled: %s (reason: %s)", live_class.id, reason)
        return live_class

    @classmethod
    def add_resource(
        cls,
        live_class: LiveClass,
        title: str,
        file=None,
        external_link: str = "",
        description: str = "",
        uploaded_by: Optional[User] = None,
    ) -> ClassResource:
        """Attach a slide deck, worksheet, or reference material to a live class."""
        if not file and not external_link:
            raise ValidationError("Either a file or an external URL link must be provided.")

        resource = ClassResource.objects.create(
            live_class=live_class,
            title=title.strip(),
            file=file,
            external_link=external_link.strip(),
            description=description.strip(),
            uploaded_by=uploaded_by,
        )
        logger.info("Class resource added to %s: '%s'", live_class.id, resource.title)
        return resource

    @classmethod
    def notify_students_scheduled(cls, live_class: LiveClass, is_reschedule: bool = False) -> int:
        """Dispatch notifications to students in the cohort or platform-wide."""
        if live_class.cohort:
            recipients = live_class.cohort.students.filter(is_active=True)
        else:
            recipients = User.objects.filter(role=UserRole.STUDENT, is_active=True)

        class_time_str = f"{live_class.scheduled_date.strftime('%d/%m/%Y')} at {live_class.start_time.strftime('%H:%M')}"
        tutor_name = (
            live_class.tutor.get_full_name() or live_class.tutor.phone_number
            if live_class.tutor
            else "Sifo Drive Tutor"
        )
        title_text = f"Live Class {'Rescheduled' if is_reschedule else 'Scheduled'}: {live_class.title}"

        count = 0
        for student in recipients:
            try:
                NotificationService.send_live_class_scheduled(
                    user=student,
                    title=title_text,
                    class_time=class_time_str,
                    tutor_name=tutor_name,
                    live_class_id=str(live_class.id),
                    language="rw",
                )
                count += 1
            except Exception as exc:
                logger.warning("Failed to dispatch live class notice to %s: %s", student.id, exc)

        logger.info("Dispatched live class schedule notice to %d students", count)
        return count

    @classmethod
    def notify_students_reminder(cls, live_class: LiveClass) -> int:
        """Dispatch SMS reminder with Google Meet link to students."""
        if not live_class.google_meet_url:
            return 0

        if live_class.cohort:
            recipients = live_class.cohort.students.filter(is_active=True)
        else:
            recipients = User.objects.filter(role=UserRole.STUDENT, is_active=True)

        count = 0
        for student in recipients:
            try:
                NotificationService.send_live_class_reminder(
                    user=student,
                    meet_link=live_class.google_meet_url,
                    live_class_id=str(live_class.id),
                    language="rw",
                )
                count += 1
            except Exception as exc:
                logger.warning("Failed to dispatch live class SMS reminder to %s: %s", student.id, exc)

        logger.info("Dispatched live class Meet reminder to %d students", count)
        return count


# ===========================================================================
# Attendance Service
# ===========================================================================

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
          - Total mandatory classes: completed or in-progress live classes
            associated with cohorts the student is enrolled in (or all completed published
            classes if the student is not assigned to a cohort).
          - Attended classes: status in (PRESENT, LATE, WATCHED_RECORDING).
          - If total mandatory classes is 0, return 1.0 (student is not penalized before classes begin).
        """
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
                AttendanceStatus.WATCHED_RECORDING,
            ],
        ).count()

        rate = round(attended_count / total_classes, 4)
        return min(rate, 1.0)

    @classmethod
    def get_student_attendance_summary(cls, student: User) -> Dict[str, Any]:
        """
        Return comprehensive attendance report for student dashboard & exam gate verification.
        """
        rate = cls.get_attendance_rate(student)
        percentage = round(rate * 100, 1)

        attendances = ClassAttendance.objects.filter(student=student)
        present_count = attendances.filter(status=AttendanceStatus.PRESENT).count()
        late_count = attendances.filter(status=AttendanceStatus.LATE).count()
        absent_count = attendances.filter(status=AttendanceStatus.ABSENT).count()
        excused_count = attendances.filter(status=AttendanceStatus.EXCUSED).count()
        watched_recording_count = attendances.filter(status=AttendanceStatus.WATCHED_RECORDING).count()

        return {
            "rate": rate,
            "percentage": percentage,
            "is_eligible_for_exam": rate >= cls.ELIGIBILITY_THRESHOLD,
            "threshold_required_percentage": cls.ELIGIBILITY_THRESHOLD * 100,
            "present_count": present_count,
            "late_count": late_count,
            "absent_count": absent_count,
            "excused_count": excused_count,
            "watched_recording_count": watched_recording_count,
            "total_attended": present_count + late_count + watched_recording_count,
        }
