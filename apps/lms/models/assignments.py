"""
apps/lms/models/assignments.py
==============================
Models managing instructor certification and teaching assignments.

Rules:
  - Training Admin assigns Curricula to certified Tutors.
  - Training Admin assigns Courses to Tutors ONLY if the course's parent
    curriculum is already assigned to that tutor.
  - An approved tutor must have at least one curriculum assigned.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.accounts.constants import UserRole
from apps.core.models import BaseModel


class TutorCurriculumAssignment(BaseModel):
    """
    Links an instructor to a curriculum they are accredited to teach.
    Managed by Training Admin.
    """

    tutor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="curriculum_assignments",
        limit_choices_to={"role": UserRole.TUTOR},
        verbose_name=_("Tutor"),
    )
    curriculum = models.ForeignKey(
        "lms.Curriculum",
        on_delete=models.CASCADE,
        related_name="tutor_assignments",
        verbose_name=_("Curriculum"),
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_tutor_curricula",
        verbose_name=_("Assigned By"),
    )
    is_active = models.BooleanField(_("Active"), default=True, db_index=True)

    class Meta(BaseModel.Meta):
        unique_together = ("tutor", "curriculum")
        verbose_name = _("Tutor Curriculum Assignment")
        verbose_name_plural = _("Tutor Curriculum Assignments")

    def __str__(self) -> str:
        return f"{self.tutor.full_name or self.tutor.phone_number} → {self.curriculum.title}"


class TutorCourseAssignment(BaseModel):
    """
    Links a tutor to a course they actively instruct.
    Hard Invariant: The course's parent curriculum MUST be actively assigned
    to this tutor.
    """

    tutor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="course_assignments",
        limit_choices_to={"role": UserRole.TUTOR},
        verbose_name=_("Tutor"),
    )
    course = models.ForeignKey(
        "lms.Course",
        on_delete=models.CASCADE,
        related_name="tutor_assignments",
        verbose_name=_("Course"),
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_tutor_courses",
        verbose_name=_("Assigned By"),
    )
    is_active = models.BooleanField(_("Active"), default=True, db_index=True)

    class Meta(BaseModel.Meta):
        unique_together = ("tutor", "course")
        verbose_name = _("Tutor Course Assignment")
        verbose_name_plural = _("Tutor Course Assignments")

    def __str__(self) -> str:
        return f"{self.tutor.full_name or self.tutor.phone_number} → {self.course.title}"

    def clean(self):
        super().clean()
        if self.course and self.course.curriculum_id:
            has_curriculum = TutorCurriculumAssignment.objects.filter(
                tutor=self.tutor,
                curriculum_id=self.course.curriculum_id,
                is_active=True,
                is_deleted=False,
            ).exists()
            if not has_curriculum:
                curr_name = (
                    self.course.curriculum.title
                    if self.course.curriculum
                    else str(self.course.curriculum_id)
                )
                raise ValidationError(
                    f"Cannot assign course '{self.course.title}' to tutor "
                    f"'{self.tutor.full_name or self.tutor.phone_number}' because its parent curriculum "
                    f"'{curr_name}' has not been assigned to this tutor. "
                    f"Please assign the curriculum first."
                )

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)
