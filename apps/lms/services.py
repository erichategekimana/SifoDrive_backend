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
        if not lesson.module.is_published or not lesson.module.course.is_published:
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
        Staff see all courses; learners see only published ones.
        """
        from apps.accounts.constants import UserRole
        from .models import Course

        if user and user.is_authenticated and user.role in (
            UserRole.TUTOR, UserRole.TRAINING_ADMIN, UserRole.SYSTEM_ADMIN
        ):
            return Course.objects.all()

        return Course.objects.filter(is_published=True)

    @classmethod
    def get_visible_modules(cls, course, user) -> QuerySet:
        """
        Return modules of a course visible to this user.
        Staff see all; learners see only published modules.
        """
        from apps.accounts.constants import UserRole

        qs = course.modules.filter(is_deleted=False)

        if user and user.is_authenticated and user.role in (
            UserRole.TUTOR, UserRole.TRAINING_ADMIN, UserRole.SYSTEM_ADMIN
        ):
            return qs

        return qs.filter(is_published=True)

    @classmethod
    def get_visible_lessons(cls, module, user) -> QuerySet:
        """
        Return lessons of a module visible to this user, applying the
        is_student_only filter where needed.
        """
        from apps.accounts.constants import UserRole
        from .models import Lesson

        qs = module.lessons.filter(is_deleted=False)

        if not (user and user.is_authenticated):
            return qs.filter(is_free_preview=True)

        if user.role in (UserRole.TUTOR, UserRole.TRAINING_ADMIN, UserRole.SYSTEM_ADMIN, UserRole.BOARD_REVIEWER):
            return qs

        if user.role == UserRole.STUDENT:
            return qs  # Students see everything

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
        published_modules = course.modules.filter(
            is_published=True, is_deleted=False
        ).count()

        if published_modules == 0:
            raise ValueError(
                f"Cannot publish '{course.title}': it must have at least one published module."
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
