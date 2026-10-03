from datetime import date
import logging
from typing import List, Optional, Tuple, Union

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from apps.accounts.constants import UserRole
from apps.accounts.models import User
from apps.live_classes.models import Cohort
from apps.live_classes.models.cohort import CohortStatus

logger = logging.getLogger("apps.live_classes.services")


class CohortService:
    """
    Business service managing student batches / cohorts, tutor assignments,
    status transitions (queue -> open -> closed / ended), and capacity constraints.
    """

    @classmethod
    @transaction.atomic
    def create_cohort(
        cls,
        name: str,
        start_date: date,
        code: Optional[str] = None,
        end_date: Optional[date] = None,
        max_capacity: int = 60,
        schedule_description: str = "",
        description: str = "",
        assigned_tutors: Optional[List[User]] = None,
        students: Optional[List[User]] = None,
        status: str = CohortStatus.QUEUE,
    ) -> Cohort:
        """
        Create a new cohort defaulting to 'queue' status and 60 student capacity.
        If status is specified as 'open', ensures only this cohort is open.
        """
        if not code:
            import uuid
            year = start_date.year if hasattr(start_date, "year") else timezone.now().year
            code = f"COH-{year}-{uuid.uuid4().hex[:6].upper()}"
        else:
            code = code.strip().upper()

        if Cohort.objects.filter(code=code).exists():
            raise ValidationError(f"Cohort with code '{code}' already exists.")

        if end_date and end_date < start_date:
            raise ValidationError("End date cannot precede start date.")

        initial_status = CohortStatus.QUEUE if status not in CohortStatus.values else status

        cohort = Cohort.objects.create(
            name=name.strip(),
            code=code,
            start_date=start_date,
            end_date=end_date,
            max_capacity=max_capacity,
            schedule_description=schedule_description.strip(),
            description=description.strip(),
            status=CohortStatus.QUEUE,
        )

        if assigned_tutors:
            cls.assign_tutors(cohort, [t.id for t in assigned_tutors])
        if students:
            cls.enroll_students(cohort, [s.id for s in students])

        if initial_status == CohortStatus.OPEN:
            cls.set_cohort_open(cohort)
        elif initial_status != CohortStatus.QUEUE:
            cohort.status = initial_status
            cohort.save(update_fields=["status", "updated_at"])

        cohort.evaluate_status(save=True)
        logger.info("Cohort created: %s (code=%s, status=%s)", cohort.name, cohort.code, cohort.status)
        return cohort

    @classmethod
    def evaluate_all_cohorts_status(cls) -> int:
        """
        Scan and evaluate all active cohorts, auto-updating statuses:
        - end_date < today -> 'ended'
        - status == 'open' and student capacity reached -> 'closed'
        Returns the number of cohorts whose status was updated.
        """
        today = timezone.now().date()
        updated_count = 0

        # Auto-end cohorts whose end_date has passed
        ended = Cohort.objects.filter(
            end_date__isnull=False,
            end_date__lt=today,
        ).exclude(status=CohortStatus.ENDED).update(status=CohortStatus.ENDED)
        updated_count += ended

        # Check all currently open cohorts for capacity or expiration
        open_cohorts = Cohort.objects.filter(status=CohortStatus.OPEN)
        for cohort in open_cohorts:
            prev_status = cohort.status
            cohort.evaluate_status(save=True)
            if cohort.status != prev_status:
                updated_count += 1

        return updated_count

    @classmethod
    def get_default_open_cohort(cls) -> Optional[Cohort]:
        """
        Retrieve the single 'open' cohort designated as default for newly registering students.
        Evaluates status dynamically to ensure it is not expired or full.
        """
        cls.evaluate_all_cohorts_status()
        cohort = Cohort.objects.filter(status=CohortStatus.OPEN, is_active=True).first()
        if not cohort:
            return None

        # Confirm evaluation
        if cohort.evaluate_status(save=True) != CohortStatus.OPEN:
            return None

        return cohort

    @classmethod
    @transaction.atomic
    def set_cohort_open(cls, cohort: Cohort) -> Cohort:
        """
        Mark this cohort as 'open' (the default cohort for new registering students).
        Enforces that only ONE cohort can be 'open' at any time.
        Any previously 'open' cohort automatically transitions to 'closed'.
        """
        today = timezone.now().date()
        if cohort.end_date and cohort.end_date < today:
            raise ValidationError("Cannot open a cohort whose scheduled end date has already passed.")

        if cohort.students.count() >= cohort.max_capacity:
            raise ValidationError(
                f"Cannot open cohort '{cohort.name}' because it has reached its maximum capacity of {cohort.max_capacity} students."
            )

        # Transition any other currently open cohorts to 'closed'
        Cohort.objects.filter(status=CohortStatus.OPEN).exclude(pk=cohort.pk).update(status=CohortStatus.CLOSED)

        cohort.status = CohortStatus.OPEN
        cohort.is_active = True
        cohort.save(update_fields=["status", "is_active", "updated_at"])
        logger.info("Cohort %s (%s) is now OPEN as default cohort.", cohort.code, cohort.name)
        return cohort

    @classmethod
    @transaction.atomic
    def set_cohort_status(cls, cohort: Cohort, new_status: str) -> Cohort:
        """
        Set cohort status to 'queue', 'open', 'closed', or 'ended'.
        """
        if new_status not in CohortStatus.values:
            raise ValidationError(f"Invalid status '{new_status}'. Allowed choices: {CohortStatus.values}.")

        if new_status == CohortStatus.OPEN:
            return cls.set_cohort_open(cohort)

        today = timezone.now().date()
        if new_status == CohortStatus.QUEUE:
            if cohort.end_date and cohort.end_date < today:
                raise ValidationError("Cannot place an ended cohort into queue.")
            if cohort.students.count() >= cohort.max_capacity:
                raise ValidationError("Cannot place a full cohort into queue.")

        cohort.status = new_status
        cohort.save(update_fields=["status", "updated_at"])
        logger.info("Cohort %s status updated to %s.", cohort.code, new_status)
        return cohort

    @classmethod
    @transaction.atomic
    def assign_student_id(cls, student: User, cohort: Cohort, year: Optional[int] = None) -> str:
        """
        Generate and assign a unique Student ID (starts with SDS + 11 characters:
        3-digit cohort identifier + 4-digit year + 4-digit student sequence).
        Example: SDS00120260001.
        """
        if student.student_id:
            return student.student_id

        from apps.core.utils import generate_student_id_for_cohort
        student_id = generate_student_id_for_cohort(cohort, year)
        student.student_id = student_id
        student.save(update_fields=["student_id", "updated_at"])

        from apps.accounts.models import StudentProfile
        StudentProfile.objects.update_or_create(
            user=student,
            defaults={"enrollment_date": timezone.now().date()},
        )
        logger.info(
            "Assigned Student ID %s to student %s in cohort %s (%s)",
            student_id,
            student.phone_number,
            cohort.identifier,
            cohort.name,
        )
        return student_id

    @classmethod
    @transaction.atomic
    def enroll_students(cls, cohort: Cohort, student_ids: List[Union[str, int]]) -> Tuple[int, List[str]]:
        """
        Enroll a list of students into the cohort, respecting max capacity.
        If max capacity is reached, automatically closes an open cohort.
        Automatically generates unique Student IDs (SDS + 11 chars) for newly enrolled students.
        Returns (count_enrolled, warnings).
        """
        normalized_ids = [getattr(s, "id", s) for s in student_ids]
        students = list(User.objects.filter(id__in=normalized_ids, role=UserRole.STUDENT))
        current_count = cohort.students.count()
        incoming_count = len(students)
        warnings = []

        if current_count + incoming_count > cohort.max_capacity:
            warnings.append(
                f"Enrolling {incoming_count} students will exceed maximum capacity ({cohort.max_capacity})."
            )

        cohort.students.add(*students)

        # Autogenerate student ID for any enrolled student who doesn't have one yet
        for student in students:
            if not student.student_id:
                cls.assign_student_id(student, cohort)

        # Re-evaluate status: if capacity reached, open cohort transitions to closed
        cohort.evaluate_status(save=True)

        logger.info(
            "Enrolled %d students into cohort %s (total: %d, status: %s)",
            incoming_count,
            cohort.code,
            cohort.students.count(),
            cohort.status,
        )
        return incoming_count, warnings

    @classmethod
    @transaction.atomic
    def enroll_student_in_default_open_cohort(cls, user: User) -> Optional[Cohort]:
        """
        Automatically enroll a newly registered or upgraded student into the current
        default 'open' cohort. If the open cohort becomes full, it automatically transitions
        to 'closed'.
        Generates and assigns unique Student ID (SDS + 11 chars).
        """
        if user.role != UserRole.STUDENT:
            return None

        open_cohort = cls.get_default_open_cohort()
        if not open_cohort:
            logger.warning(
                "No open cohort found to auto-enroll student %s (phone=%s). Student will wait for cohort assignment.",
                str(user.id)[:8],
                user.phone_number,
            )
            return None

        if open_cohort.students.filter(pk=user.pk).exists():
            if not user.student_id:
                cls.assign_student_id(user, open_cohort)
            return open_cohort

        open_cohort.students.add(user)
        if not user.student_id:
            cls.assign_student_id(user, open_cohort)
        open_cohort.evaluate_status(save=True)

        logger.info(
            "Auto-enrolled student %s into default open cohort %s (total: %d, status: %s, student_id: %s).",
            str(user.id)[:8],
            open_cohort.code,
            open_cohort.students.count(),
            open_cohort.status,
            user.student_id,
        )
        return open_cohort

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

    @classmethod
    def get_ongoing_students_count(cls, cohort: Cohort) -> int:
        """
        Count students in the cohort who have NOT yet completed or withdrawn from the course.
        A student is considered withdrawn if their account status is DEACTIVATED,
        SUSPENDED, or BLACKLISTED, or if is_active is False.
        A student is considered completed if their overall course completion is 100%.
        """
        from apps.accounts.constants import AccountStatus, UserRole
        from apps.lms.services import ProgressService

        students = cohort.students.filter(role=UserRole.STUDENT)
        ongoing_count = 0
        for student in students:
            # Check if withdrawn or inactive
            if not student.is_active or student.status in [
                AccountStatus.DEACTIVATED,
                AccountStatus.SUSPENDED,
                AccountStatus.BLACKLISTED,
            ]:
                continue

            # Check if completed
            completion = ProgressService.get_overall_completion(student)
            foundational = ProgressService.get_foundational_completion(student)
            if completion >= 1.0 or foundational >= 1.0:
                continue

            ongoing_count += 1

        return ongoing_count

    @classmethod
    def can_deactivate_cohort(cls, cohort: Cohort) -> Tuple[bool, int]:
        """
        Return (can_deactivate, ongoing_count).
        A cohort can be deactivated ONLY when all students in it have completed
        or withdrawn from the course.
        """
        ongoing = cls.get_ongoing_students_count(cohort)
        return (ongoing == 0, ongoing)
