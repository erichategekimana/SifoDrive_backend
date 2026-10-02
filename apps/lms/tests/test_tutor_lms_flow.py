import datetime
import pytest
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.accounts.constants import UserRole
from apps.accounts.models import User
from apps.live_classes.models import Cohort
from apps.lms.models import (
    CohortActivity,
    CohortModuleRelease,
    CohortQuizSchedule,
    Course,
    Curriculum,
    Module,
    Quiz,
    StudentActivitySubmission,
    TutorCourseAssignment,
    TutorCurriculumAssignment,
)
from apps.lms.services import (
    CohortActivityService,
    CohortMaterialService,
    ContentGateService,
    TutorAssignmentService,
)


@pytest.fixture
def training_admin(db):
    return User.objects.create_user(
        phone_number="+250788990001",
        first_name="Training",
        last_name="Admin",
        role=UserRole.TRAINING_ADMIN,
        password="TestPassword123!",
    )


@pytest.fixture
def tutor_1(db):
    return User.objects.create_user(
        phone_number="+250788990002",
        first_name="Jean",
        last_name="Tutor",
        role=UserRole.TUTOR,
        password="TestPassword123!",
    )


@pytest.fixture
def tutor_2(db):
    return User.objects.create_user(
        phone_number="+250788990003",
        first_name="Eric",
        last_name="Tutor",
        role=UserRole.TUTOR,
        password="TestPassword123!",
    )


@pytest.fixture
def student_1(db):
    return User.objects.create_user(
        phone_number="+250788990004",
        first_name="Alice",
        last_name="Student",
        role=UserRole.STUDENT,
        password="TestPassword123!",
    )


@pytest.fixture
def student_2(db):
    return User.objects.create_user(
        phone_number="+250788990005",
        first_name="Bob",
        last_name="Student",
        role=UserRole.STUDENT,
        password="TestPassword123!",
    )


@pytest.fixture
def curriculum_a(db):
    return Curriculum.objects.create(
        code="CURR-A",
        title="Curriculum A - Rwanda Universal",
        is_published=True,
    )


@pytest.fixture
def curriculum_b(db):
    return Curriculum.objects.create(
        code="CURR-B",
        title="Curriculum B - Advanced Driving",
        is_published=True,
    )


@pytest.fixture
def course_a1(db, curriculum_a):
    return Course.objects.create(
        curriculum=curriculum_a,
        code="CRS-A1",
        title="Course A1 - Road Rules",
        is_published=True,
    )


@pytest.fixture
def course_b1(db, curriculum_b):
    return Course.objects.create(
        curriculum=curriculum_b,
        code="CRS-B1",
        title="Course B1 - Heavy Vehicles",
        is_published=True,
    )


@pytest.fixture
def cohort_1(db, tutor_1, student_1):
    cohort = Cohort.objects.create(
        name="Cohort 1 (Morning)",
        code="COH-001",
        start_date=timezone.now().date(),
        is_active=True,
    )
    cohort.assigned_tutors.add(tutor_1)
    cohort.students.add(student_1)
    return cohort


@pytest.fixture
def cohort_2(db, tutor_2, student_2):
    cohort = Cohort.objects.create(
        name="Cohort 2 (Evening)",
        code="COH-002",
        start_date=timezone.now().date(),
        is_active=True,
    )
    cohort.assigned_tutors.add(tutor_2)
    cohort.students.add(student_2)
    return cohort


@pytest.mark.django_db
def test_cannot_assign_course_without_parent_curriculum(training_admin, tutor_1, curriculum_a, curriculum_b, course_b1):
    # 1. Assign Curriculum A to tutor_1
    TutorAssignmentService.assign_curricula_to_tutor(
        tutor=tutor_1,
        curriculum_ids=[curriculum_a.id],
        assigned_by=training_admin,
    )

    # 2. Attempting to assign course_b1 (from Curriculum B) must fail
    with pytest.raises(ValidationError) as exc_info:
        TutorAssignmentService.assign_courses_to_tutor(
            tutor=tutor_1,
            course_ids=[course_b1.id],
            assigned_by=training_admin,
        )
    assert "parent curriculum" in str(exc_info.value)

    # Model level clean() also rejects it
    with pytest.raises(DjangoValidationError):
        assignment = TutorCourseAssignment(tutor=tutor_1, course=course_b1)
        assignment.full_clean()


@pytest.mark.django_db
def test_student_sees_only_courses_of_their_cohort_tutors(
    training_admin, tutor_1, tutor_2, student_1, student_2,
    curriculum_a, curriculum_b, course_a1, course_b1, cohort_1, cohort_2
):
    # Assign curriculum A & course A1 to tutor_1
    TutorAssignmentService.assign_curricula_to_tutor(tutor_1, [curriculum_a.id], training_admin)
    TutorAssignmentService.assign_courses_to_tutor(tutor_1, [course_a1.id], training_admin)

    # Assign curriculum B & course B1 to tutor_2
    TutorAssignmentService.assign_curricula_to_tutor(tutor_2, [curriculum_b.id], training_admin)
    TutorAssignmentService.assign_courses_to_tutor(tutor_2, [course_b1.id], training_admin)

    # student_1 (Cohort 1, taught by tutor_1) should see course_a1 ONLY
    student_1_courses = list(ContentGateService.get_visible_courses(student_1))
    assert course_a1 in student_1_courses
    assert course_b1 not in student_1_courses

    # student_2 (Cohort 2, taught by tutor_2) should see course_b1 ONLY
    student_2_courses = list(ContentGateService.get_visible_courses(student_2))
    assert course_b1 in student_2_courses
    assert course_a1 not in student_2_courses


@pytest.mark.django_db
def test_tutor_cohort_module_release_and_quiz_extension(tutor_1, cohort_1, course_a1):
    module = Module.objects.create(course=course_a1, title="Module Priority", is_published=True)
    quiz = Quiz.objects.create(
        course=course_a1,
        title="Priority Quiz",
        allow_tutor_scheduling=True,
        is_published=True,
    )

    # Tutor locks module for cohort_1
    rel = CohortMaterialService.update_cohort_module_release(
        cohort=cohort_1,
        module=module,
        is_published=True,
        is_locked=True,
        user=tutor_1,
    )
    assert rel.is_locked is True

    # Tutor schedules quiz for cohort_1
    now = timezone.now()
    deadline = now + datetime.timedelta(days=2)
    sch = CohortMaterialService.schedule_cohort_quiz(
        cohort=cohort_1,
        quiz=quiz,
        open_date=now,
        deadline=deadline,
        is_published=True,
        user=tutor_1,
    )
    assert sch.deadline == deadline
    assert sch.status_for_cohort == "OPEN"

    # Tutor extends deadline for cohort_1
    extended = deadline + datetime.timedelta(days=3)
    sch_ext = CohortMaterialService.extend_cohort_quiz_deadline(
        cohort=cohort_1,
        quiz=quiz,
        extended_deadline=extended,
        reason="Heavy rain, class needed more practice time",
        user=tutor_1,
    )
    assert sch_ext.effective_deadline == extended
    assert sch_ext.extension_reason == "Heavy rain, class needed more practice time"


@pytest.mark.django_db
def test_tutor_activity_creation_submission_and_grading(tutor_1, student_1, cohort_1, course_a1):
    # Tutor creates cohort activity
    activity = CohortActivityService.create_activity(
        cohort=cohort_1,
        course=course_a1,
        title="Vehicle Pre-Drive Inspection Drill",
        description="Inspect oil, brakes, and headlights. List steps.",
        activity_type="PRACTICAL_DRILL",
        submission_type="TEXT_RESPONSE",
        total_points=50,
        passing_points=35,
        due_date=timezone.now() + datetime.timedelta(days=3),
        tutor=tutor_1,
    )
    assert activity.cohort == cohort_1
    assert activity.created_by == tutor_1

    # Student 1 submits response
    submission = CohortActivityService.submit_activity(
        activity=activity,
        student=student_1,
        submission_text="Checked dipstick level, brake fluid reservoir, and light bulbs.",
    )
    assert submission.status == StudentActivitySubmission.SubmissionStatus.SUBMITTED
    assert submission.student == student_1

    # Tutor grades submission
    graded = CohortActivityService.grade_submission(
        submission=submission,
        score=48,
        feedback="Excellent thorough inspection checklist!",
        tutor=tutor_1,
    )
    assert graded.status == StudentActivitySubmission.SubmissionStatus.GRADED
    assert graded.score == 48
    assert graded.tutor_feedback == "Excellent thorough inspection checklist!"
    assert graded.graded_by == tutor_1
