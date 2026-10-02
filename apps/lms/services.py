"""
apps/lms/services.py
=====================
LMS business logic — content gating, progress tracking, course management.

Rules:
  - Views call services; services never call views.
  - All DB mutations go through service methods, never raw ORM in views.
  - Content access decisions are centralised in ContentGateService.
  - Progress calculations are centralised in ProgressService.
"""

import logging
from typing import Optional

from django.db import transaction
from django.db.models import Count, Q, QuerySet

logger = logging.getLogger("apps.lms")


# ===========================================================================
# ContentGateService — who can see what
# ===========================================================================

class ContentGateService:
    """
    Centralised access-control decisions for LMS content.

    Access matrix (enforced here, reflected in serializers and views):
      is_free_preview  → everyone
      is_student_only  → STUDENT, TUTOR, BOARD_REVIEWER, SYSTEM_ADMIN
      (default)        → any authenticated user (GUEST + STUDENT + staff)
      quiz questions   → STUDENT, TUTOR, SYSTEM_ADMIN only
      draft content    → TUTOR, SYSTEM_ADMIN only
    """

    @classmethod
    def can_access_lesson(cls, user, lesson) -> bool:
        """
        Return True if `user` is authorised to open `lesson`.
        Also checks that the parent Module and Course are published
        (unless the user is staff, who can preview drafts).
        """
        from apps.accounts.constants import UserRole

        is_staff = (
            user
            and user.is_authenticated
            and user.role in (
                UserRole.TUTOR,
                UserRole.TRAINING_ADMIN,
                UserRole.BOARD_REVIEWER,
                UserRole.SYSTEM_ADMIN,
            )
        )

        # Staff bypass: always allow, even for draft content
        if is_staff:
            return True

        # Draft content: invisible to learners
        if (
            not lesson.module.is_published
            or not lesson.module.course.is_published
            or (lesson.module.course.curriculum and not lesson.module.course.curriculum.is_published)
        ):
            return False

        # If parent module is student only, block non-students
        if getattr(lesson.module, "is_student_only", False) and user.role != UserRole.STUDENT:
            return False

        # Free preview: anyone (even unauthenticated)
        if lesson.is_free_preview:
            return True

        if not (user and user.is_authenticated):
            return False

        # Student-only: block guests
        if lesson.is_student_only:
            return user.role == UserRole.STUDENT

        # Regular lesson: any authenticated user
        return True

    @classmethod
    def get_visible_courses(cls, user) -> QuerySet:
        """
        Return the Course queryset appropriate for the requesting user.
        - Staff & Training/System Admins see all non-deleted courses.
        - Tutors see courses actively assigned to them by Training Admin.
        - Students see courses assigned to the active tutors of their enrolled cohort(s).
        - Guests & unauthenticated users see published courses from published curricula.
        """
        from apps.accounts.constants import UserRole
        from apps.accounts.models import User
        from .models import Course

        if not user or not user.is_authenticated:
            return Course.objects.filter(
                is_published=True,
                is_deleted=False,
                curriculum__is_published=True,
                curriculum__is_deleted=False,
            )

        if user.is_staff or user.is_superuser or user.role in (
            UserRole.SYSTEM_ADMIN,
            UserRole.TRAINING_ADMIN,
            UserRole.BOARD_REVIEWER,
        ):
            return Course.objects.filter(is_deleted=False)

        if user.role == UserRole.TUTOR:
            return Course.objects.filter(
                is_deleted=False,
                is_published=True,
                curriculum__is_published=True,
                curriculum__is_deleted=False,
                tutor_assignments__tutor=user,
                tutor_assignments__is_active=True,
            ).distinct()

        if user.role == UserRole.STUDENT:
            cohorts = user.enrolled_cohorts.filter(is_active=True)
            if not cohorts.exists():
                return Course.objects.none()

            cohort_tutors = User.objects.filter(
                assigned_cohorts__in=cohorts,
                is_active=True,
            )
            return Course.objects.filter(
                is_deleted=False,
                is_published=True,
                curriculum__is_published=True,
                curriculum__is_deleted=False,
                tutor_assignments__tutor__in=cohort_tutors,
                tutor_assignments__is_active=True,
            ).distinct()

        # Default fallback for GUEST and other roles
        return Course.objects.filter(
            is_published=True,
            is_deleted=False,
            curriculum__is_published=True,
            curriculum__is_deleted=False,
        )

    @classmethod
    def get_visible_modules(cls, course, user) -> QuerySet:
        """
        Return modules of a course visible to this user.
        Staff see all; learners see only published modules.
        Guests and unauthenticated users see only modules that are not student-only.
        """
        from apps.accounts.constants import UserRole

        qs = course.modules.filter(is_deleted=False)

        if user and user.is_authenticated and (
            user.is_staff
            or user.is_superuser
            or user.role in (
                UserRole.TUTOR,
                UserRole.TRAINING_ADMIN,
                UserRole.SYSTEM_ADMIN,
                UserRole.BOARD_REVIEWER,
            )
        ):
            return qs

        # If parent course or parent curriculum is not published, learners cannot view modules
        if not course.is_published or (course.curriculum and not course.curriculum.is_published):
            return course.modules.none()

        qs = qs.filter(is_published=True)

        # Guests and anonymous users cannot see student-only modules
        if not (user and user.is_authenticated) or user.role == UserRole.GUEST:
            qs = qs.filter(is_student_only=False)

        return qs

    @classmethod
    def get_visible_lessons(cls, module, user) -> QuerySet:
        """
        Return lessons of a module visible to this user, applying both
        module-level and lesson-level is_student_only filtering.
        """
        from apps.accounts.constants import UserRole
        from .models import Lesson

        qs = module.lessons.filter(is_deleted=False)

        is_staff = user and user.is_authenticated and (
            user.is_staff
            or user.is_superuser
            or user.role in (
                UserRole.TUTOR,
                UserRole.TRAINING_ADMIN,
                UserRole.SYSTEM_ADMIN,
                UserRole.BOARD_REVIEWER,
            )
        )
        if is_staff:
            return qs

        # If the parent module is student only, guests cannot see any of its lessons
        is_student = user and user.is_authenticated and user.role == UserRole.STUDENT
        if getattr(module, "is_student_only", False) and not is_student:
            return qs.none()

        if not (user and user.is_authenticated):
            return qs.filter(is_free_preview=True)

        if is_student:
            return qs  # Students see all published lessons

        # Guest: exclude student-only lessons
        return qs.filter(is_student_only=False)


# ===========================================================================
# ProgressService — tracking and eligibility
# ===========================================================================

class ProgressService:
    """
    Compute and record student learning progress.
    Called by the exam eligibility checker and the dashboard.
    """

    @classmethod
    def get_foundational_completion(cls, user) -> float:
        """
        Return the fraction (0.0–1.0) of foundational lesson completion.

        A student is exam-eligible only when this returns 1.0 (100%).
        Foundational lessons are those within is_foundational=True modules.

        Returns 0.0 for non-students or users with no progress.
        """
        from apps.accounts.constants import UserRole
        from .models import Lesson, StudentProgress

        if not user or user.role != UserRole.STUDENT:
            return 0.0

        foundational_lessons = Lesson.objects.filter(
            is_deleted=False,
            module__is_foundational=True,
            module__is_deleted=False,
            module__is_published=True,
            module__course__is_published=True,
        )
        total = foundational_lessons.count()
        if total == 0:
            return 0.0

        completed = StudentProgress.objects.filter(
            student=user,
            lesson__in=foundational_lessons,
            is_completed=True,
        ).count()

        return round(completed / total, 4)

    @classmethod
    def get_overall_completion(cls, user, course=None) -> float:
        """
        Return the overall lesson completion fraction for a user.
        Pass `course` to scope to a single course.

        Returns 0.0 if no published lessons exist.
        """
        from .models import Lesson, StudentProgress

        lesson_filter = {
            "is_deleted": False,
            "module__is_deleted": False,
            "module__is_published": True,
            "module__course__is_published": True,
        }
        if course:
            lesson_filter["module__course"] = course

        lessons = Lesson.objects.filter(**lesson_filter)
        total = lessons.count()
        if total == 0:
            return 0.0

        completed = StudentProgress.objects.filter(
            student=user,
            lesson__in=lessons,
            is_completed=True,
        ).count()

        return round(completed / total, 4)

    @classmethod
    def get_progress_summary(cls, user, course=None) -> dict:
        """
        Return a rich progress summary dict for the dashboard widget.

        {
            "total_lessons": 120,
            "completed_lessons": 45,
            "overall_pct": 37.5,
            "foundational_pct": 60.0,
            "is_exam_eligible": false,
            "time_spent_hours": 3.2,
        }
        """
        from .models import Lesson, StudentProgress

        lesson_filter = {
            "is_deleted": False,
            "module__is_deleted": False,
            "module__is_published": True,
            "module__course__is_published": True,
        }
        if course:
            lesson_filter["module__course"] = course

        lessons = Lesson.objects.filter(**lesson_filter)
        total = lessons.count()

        progress_qs = StudentProgress.objects.filter(
            student=user,
            lesson__in=lessons,
        )

        completed_qs = progress_qs.filter(is_completed=True)
        completed = completed_qs.count()
        overall_pct = round((completed / total * 100), 1) if total else 0.0

        total_seconds = sum(p.time_spent_seconds for p in progress_qs)
        foundational_pct = round(cls.get_foundational_completion(user) * 100, 1)

        return {
            "total_lessons":      total,
            "completed_lessons":  completed,
            "overall_pct":        overall_pct,
            "foundational_pct":   foundational_pct,
            "is_exam_eligible":   foundational_pct >= 100.0,
            "time_spent_hours":   round(total_seconds / 3600, 1),
        }

    @classmethod
    @transaction.atomic
    def mark_lesson_complete(
        cls,
        student,
        lesson,
        time_spent_seconds: int = 0,
    ) -> "StudentProgress":
        """
        Mark a lesson as completed for a student.
        Creates a StudentProgress record if one does not exist.
        Idempotent: calling multiple times is safe.
        """
        from .models import StudentProgress

        progress, _ = StudentProgress.objects.get_or_create(
            student=student,
            lesson=lesson,
        )
        progress.mark_complete(time_spent=time_spent_seconds)
        logger.info(
            "Lesson completed | student=%s lesson=%s",
            str(student.id)[:8],
            str(lesson.id)[:8],
        )
        return progress

    @classmethod
    @transaction.atomic
    def record_quiz_attempt(
        cls,
        student,
        lesson,
        score: int,
        time_spent_seconds: int = 0,
    ) -> "StudentProgress":
        """
        Record a quiz attempt on a QUIZ-type lesson.
        Keeps the best score across multiple attempts.
        Marks completed if score >= 70%.
        """
        from .models import StudentProgress

        if not 0 <= score <= 100:
            raise ValueError(f"Quiz score must be 0–100, got {score}.")

        progress, _ = StudentProgress.objects.get_or_create(
            student=student,
            lesson=lesson,
        )
        progress.record_quiz_attempt(score=score, time_spent=time_spent_seconds)
        logger.info(
            "Quiz attempt recorded | student=%s lesson=%s score=%s",
            str(student.id)[:8],
            str(lesson.id)[:8],
            score,
        )
        return progress

    @classmethod
    def get_module_completion(cls, user, module) -> dict:
        """
        Return completion stats for a specific module.

        {
            "total": 10,
            "completed": 7,
            "pct": 70.0,
            "is_complete": false
        }
        """
        from .models import Lesson, StudentProgress

        lessons = module.lessons.filter(is_deleted=False)
        total = lessons.count()
        if total == 0:
            return {"total": 0, "completed": 0, "pct": 0.0, "is_complete": False}

        completed = StudentProgress.objects.filter(
            student=user,
            lesson__in=lessons,
            is_completed=True,
        ).count()

        pct = round(completed / total * 100, 1)
        return {
            "total":       total,
            "completed":   completed,
            "pct":         pct,
            "is_complete": completed == total,
        }


# ===========================================================================
# CourseService — content management operations
# ===========================================================================

class CourseService:
    """
    Business operations for courses and their content.
    Publish/unpublish logic is here, not in views.
    """

    @classmethod
    @transaction.atomic
    def publish_course(cls, course, published_by) -> "Course":
        """
        Publish a course. Also ensures all its modules and lessons
        meet minimum content requirements before publishing.

        Raises ValueError if the course has no published modules.
        """
        from .models import Course

        if not isinstance(course, Course):
            course = Course.objects.select_related("curriculum").get(id=course)

        if course.curriculum and not course.curriculum.is_published:
            raise ValueError(
                f"Cannot publish course '{course.title}' because its parent curriculum '{course.curriculum.title}' is not published. A course cannot be published under an unpublished curriculum."
            )

        total_modules = course.modules.filter(is_deleted=False).count()
        if total_modules == 0:
            raise ValueError(
                f"Cannot publish empty course '{course.title}'. Training admin must add curriculum modules before this course can be published."
            )

        published_modules = course.modules.filter(
            is_published=True, is_deleted=False
        ).count()

        if published_modules == 0:
            raise ValueError(
                f"Cannot publish '{course.title}': it has {total_modules} module(s) but none are published. Training admin must publish at least one module before the course can go live."
            )

        course.publish(published_by=published_by)
        logger.info(
            "Course published | course=%s by=%s",
            str(course.id)[:8],
            str(published_by.id)[:8],
        )
        return course

    @classmethod
    def unpublish_course(cls, course, unpublished_by) -> "Course":
        """Unpublish a course (move back to draft)."""
        course.unpublish()
        logger.info(
            "Course unpublished | course=%s by=%s",
            str(course.id)[:8],
            str(unpublished_by.id)[:8],
        )
        return course

    @classmethod
    @transaction.atomic
    def publish_module(cls, module, published_by) -> "Module":
        """
        Publish a single module.
        Raises ValueError if module has no lessons.
        """
        if module.lessons.filter(is_deleted=False).count() == 0:
            raise ValueError(
                f"Cannot publish '{module.title}': it must have at least one lesson."
            )
        module.publish(published_by=published_by)
        return module

    @classmethod
    def get_course_stats(cls, course) -> dict:
        """
        Return content statistics for a course (admin/tutor dashboard).

        {
            "total_modules": 5,
            "published_modules": 3,
            "total_lessons": 42,
            "lesson_breakdown": {
                "TEXT": 20, "VIDEO": 10, "QUIZ": 8, ...
            },
            "total_questions": 120,
            "active_students": 250,
        }
        """
        from .models import Lesson, QuizQuestion, LessonQuestion, StudentProgress

        modules = course.modules.filter(is_deleted=False)
        lessons = Lesson.objects.filter(
            module__in=modules, is_deleted=False
        )

        breakdown = {}
        for lt in lessons.values("lesson_type"):
            breakdown[lt["lesson_type"]] = breakdown.get(lt["lesson_type"], 0) + 1

        question_count = LessonQuestion.objects.filter(
            lesson__in=lessons.filter(lesson_type="QUIZ"),
            question__is_active=True,
        ).count()

        active_students = StudentProgress.objects.filter(
            lesson__in=lessons,
        ).values("student").distinct().count()

        return {
            "total_modules":      modules.count(),
            "published_modules":  modules.filter(is_published=True).count(),
            "total_lessons":      lessons.count(),
            "lesson_breakdown":   breakdown,
            "total_questions":    question_count,
            "active_students":    active_students,
        }


# ===========================================================================
# TutorAssignmentService — Curricula and Courses assignment to Tutors
# ===========================================================================

class TutorAssignmentService:
    """
    Manages accreditation and course assignments for tutors by Training Admin.
    Enforces the hierarchy:
      1. Training Admin assigns Curricula to Tutor.
      2. Training Admin assigns Courses from those Curricula to Tutor.
         (Cannot assign course if parent curriculum is not assigned to this tutor).
    """

    @classmethod
    @transaction.atomic
    def assign_curricula_to_tutor(cls, tutor, curriculum_ids: list, assigned_by=None) -> list:
        from apps.accounts.constants import UserRole
        from apps.accounts.models import User
        from .models import Curriculum, TutorCurriculumAssignment, TutorCourseAssignment

        if isinstance(tutor, (str, int)):
            tutor = User.objects.get(id=tutor)

        if tutor.role != UserRole.TUTOR and not tutor.is_staff:
            from rest_framework.exceptions import ValidationError
            raise ValidationError(f"User {tutor.phone_number} is not a tutor.")

        curricula = Curriculum.objects.filter(id__in=curriculum_ids, is_deleted=False)
        valid_ids = set(curricula.values_list("id", flat=True))

        # Deactivate unselected assignments
        TutorCurriculumAssignment.objects.filter(tutor=tutor, is_active=True).exclude(
            curriculum_id__in=valid_ids
        ).update(is_active=False)

        # Deactivate courses whose curricula were removed
        TutorCourseAssignment.objects.filter(
            tutor=tutor, is_active=True
        ).exclude(course__curriculum_id__in=valid_ids).update(is_active=False)

        # Activate or create selected assignments
        assigned = []
        for curr in curricula:
            assignment, _ = TutorCurriculumAssignment.objects.update_or_create(
                tutor=tutor,
                curriculum=curr,
                defaults={"is_active": True, "assigned_by": assigned_by},
            )
            assigned.append(assignment)

        logger.info(
            "Curricula assigned | tutor=%s count=%d by=%s",
            tutor.id, len(assigned), getattr(assigned_by, "id", None)
        )
        return assigned

    @classmethod
    @transaction.atomic
    def assign_courses_to_tutor(cls, tutor, course_ids: list, assigned_by=None) -> list:
        from rest_framework.exceptions import ValidationError
        from apps.accounts.constants import UserRole
        from apps.accounts.models import User
        from .models import Course, TutorCurriculumAssignment, TutorCourseAssignment

        if isinstance(tutor, (str, int)):
            tutor = User.objects.get(id=tutor)

        if tutor.role != UserRole.TUTOR and not tutor.is_staff:
            raise ValidationError(f"User {tutor.phone_number} is not a tutor.")

        active_curr_ids = set(
            TutorCurriculumAssignment.objects.filter(
                tutor=tutor, is_active=True, is_deleted=False
            ).values_list("curriculum_id", flat=True)
        )

        courses = Course.objects.filter(id__in=course_ids, is_deleted=False).select_related("curriculum")
        valid_courses = []

        for crs in courses:
            if crs.curriculum_id not in active_curr_ids:
                curr_title = crs.curriculum.title if crs.curriculum else "Unknown"
                raise ValidationError(
                    f"Cannot assign course '{crs.title}' to tutor '{tutor.full_name or tutor.phone_number}' "
                    f"because its parent curriculum '{curr_title}' is not assigned to this tutor. "
                    f"Please assign the curriculum to this tutor first."
                )
            valid_courses.append(crs)

        valid_course_ids = {c.id for c in valid_courses}

        # Deactivate unselected courses
        TutorCourseAssignment.objects.filter(tutor=tutor, is_active=True).exclude(
            course_id__in=valid_course_ids
        ).update(is_active=False)

        assigned = []
        for crs in valid_courses:
            assignment, _ = TutorCourseAssignment.objects.update_or_create(
                tutor=tutor,
                course=crs,
                defaults={"is_active": True, "assigned_by": assigned_by},
            )
            assigned.append(assignment)

        logger.info(
            "Courses assigned | tutor=%s count=%d by=%s",
            tutor.id, len(assigned), getattr(assigned_by, "id", None)
        )
        return assigned


# ===========================================================================
# CohortMaterialService — Cohort Module release & Quiz scheduling
# ===========================================================================

class CohortMaterialService:
    """
    Manages cohort-specific module releases, locking, and quiz schedules.
    Operated by Tutors per selected Cohort.
    """

    @classmethod
    @transaction.atomic
    def update_cohort_module_release(
        cls, cohort, module, is_published: bool, is_locked: bool = False, unlock_date=None, user=None
    ):
        from .models import CohortModuleRelease
        release, _ = CohortModuleRelease.objects.update_or_create(
            cohort=cohort,
            module=module,
            defaults={
                "is_published": is_published,
                "is_locked": is_locked,
                "unlock_date": unlock_date,
                "updated_by": user,
            },
        )
        return release

    @classmethod
    @transaction.atomic
    def schedule_cohort_quiz(
        cls, cohort, quiz, open_date=None, deadline=None, is_published=True, is_locked=False, user=None
    ):
        from rest_framework.exceptions import PermissionDenied
        from apps.accounts.constants import UserRole
        from .models import CohortQuizSchedule

        if not quiz.allow_tutor_scheduling and user and user.role == UserRole.TUTOR:
            raise PermissionDenied(
                "Training Admin has restricted scheduling for this quiz to a global schedule."
            )

        schedule, _ = CohortQuizSchedule.objects.update_or_create(
            cohort=cohort,
            quiz=quiz,
            defaults={
                "open_date": open_date,
                "deadline": deadline,
                "is_published": is_published,
                "is_locked": is_locked,
                "scheduled_by": user,
            },
        )
        return schedule

    @classmethod
    @transaction.atomic
    def extend_cohort_quiz_deadline(cls, cohort, quiz, extended_deadline, reason="", user=None):
        from .models import CohortQuizSchedule
        schedule, _ = CohortQuizSchedule.objects.get_or_create(
            cohort=cohort,
            quiz=quiz,
            defaults={"is_published": True, "scheduled_by": user},
        )
        schedule.extended_deadline = extended_deadline
        schedule.extension_reason = reason
        schedule.scheduled_by = user
        schedule.save(update_fields=["extended_deadline", "extension_reason", "scheduled_by", "updated_at"])
        return schedule


# ===========================================================================
# CohortActivityService — Tutor Activity creation, submission, and grading
# ===========================================================================

class CohortActivityService:
    """
    Manages custom learning activities, homework assignments, and drills created by Tutors.
    """

    @classmethod
    @transaction.atomic
    def create_activity(
        cls,
        cohort,
        course,
        module=None,
        title="",
        description="",
        title_kinyarwanda="",
        description_kinyarwanda="",
        activity_type="ASSIGNMENT",
        submission_type="TEXT_RESPONSE",
        total_points=100,
        passing_points=70,
        due_date=None,
        allow_late_submission=False,
        is_published=True,
        is_locked=False,
        tutor=None,
    ):
        from .models import CohortActivity
        activity = CohortActivity.objects.create(
            cohort=cohort,
            course=course,
            module=module,
            title=title,
            description=description,
            title_kinyarwanda=title_kinyarwanda,
            description_kinyarwanda=description_kinyarwanda,
            activity_type=activity_type,
            submission_type=submission_type,
            total_points=total_points,
            passing_points=passing_points,
            due_date=due_date,
            allow_late_submission=allow_late_submission,
            is_published=is_published,
            is_locked=is_locked,
            created_by=tutor,
        )
        return activity

    @classmethod
    @transaction.atomic
    def submit_activity(cls, activity, student, submission_text="", attachment=None):
        from rest_framework.exceptions import ValidationError
        from django.utils import timezone
        from .models import StudentActivitySubmission

        if not activity.cohort.students.filter(id=student.id).exists():
            raise ValidationError("You are not enrolled in this cohort.")

        if not activity.is_published or activity.is_locked:
            raise ValidationError("This activity is currently locked or not available.")

        now = timezone.now()
        if activity.due_date and activity.due_date < now and not activity.allow_late_submission:
            raise ValidationError("Submissions are closed. The due date has passed.")

        defaults = {
            "submission_text": submission_text,
            "status": StudentActivitySubmission.SubmissionStatus.SUBMITTED,
            "submitted_at": now,
        }
        if attachment:
            defaults["attachment"] = attachment

        submission, _ = StudentActivitySubmission.objects.update_or_create(
            activity=activity,
            student=student,
            defaults=defaults,
        )
        return submission

    @classmethod
    @transaction.atomic
    def grade_submission(cls, submission, score, feedback="", tutor=None):
        from django.utils import timezone
        from .models import StudentActivitySubmission

        submission.score = score
        submission.tutor_feedback = feedback
        submission.status = StudentActivitySubmission.SubmissionStatus.GRADED
        submission.graded_by = tutor
        submission.graded_at = timezone.now()
        submission.save(update_fields=["score", "tutor_feedback", "status", "graded_by", "graded_at", "updated_at"])
        return submission

