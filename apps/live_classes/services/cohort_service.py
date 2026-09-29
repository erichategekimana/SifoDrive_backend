from datetime import date
import logging
from typing import List, Optional, Tuple, Union

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import QuerySet

from apps.accounts.constants import UserRole
from apps.accounts.models import User
from apps.live_classes.models import Cohort

logger = logging.getLogger("apps.live_classes.services")


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
