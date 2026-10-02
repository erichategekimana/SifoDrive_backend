import pytest
from rest_framework import status
from rest_framework.test import APIClient
from django.core.exceptions import ValidationError

from apps.accounts.models import User
from apps.accounts.constants import UserRole
from apps.lms.models import Curriculum, Course, Module
from apps.lms.services import CourseService, ContentGateService


@pytest.fixture
def system_admin(db):
    return User.objects.create_user(
        phone_number="+250788000001",
        first_name="Sys",
        last_name="Admin",
        role=UserRole.SYSTEM_ADMIN,
        password="TestPassword123!",
    )


@pytest.fixture
def training_admin(db):
    return User.objects.create_user(
        phone_number="+250788000002",
        first_name="Training",
        last_name="Admin",
        role=UserRole.TRAINING_ADMIN,
        password="TestPassword123!",
    )


@pytest.fixture
def student(db):
    return User.objects.create_user(
        phone_number="+250788000003",
        first_name="Student",
        last_name="User",
        role=UserRole.STUDENT,
        password="TestPassword123!",
    )


@pytest.mark.django_db
def test_course_cannot_be_published_under_unpublished_curriculum(system_admin):
    curriculum = Curriculum.objects.create(
        code="CURR-TEST-1",
        title="Testing Curriculum",
        title_kinyarwanda="Integanyanyigisho Igerageza",
        is_published=False,
    )
    course = Course.objects.create(
        curriculum=curriculum,
        code="CRS-TEST-1",
        title="Testing Course",
        title_kinyarwanda="Isomo ry'Igerageza",
        is_published=False,
    )

    # 1. Model-level publish attempt should raise ValidationError
    with pytest.raises(ValidationError):
        course.publish()

    # 2. Service-level publish attempt should raise ValueError
    with pytest.raises(ValueError):
        CourseService.publish_course(course.id, published_by=system_admin)

    # 3. API endpoint should reject course publishing if parent curriculum is unpublished
    client = APIClient()
    client.force_authenticate(user=system_admin)
    response = client.post(f"/api/v1/lms/courses/{course.id}/publish/")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_curriculum_unpublish_cascades_to_child_courses(system_admin):
    curriculum = Curriculum.objects.create(
        code="CURR-TEST-2",
        title="Curriculum 2",
        is_published=True,
    )
    course = Course.objects.create(
        curriculum=curriculum,
        code="CRS-TEST-2",
        title="Course 2",
        is_published=True,
    )

    # Unpublishing curriculum should cascade and unpublish child course
    curriculum.unpublish()
    course.refresh_from_db()
    assert curriculum.is_published is False
    assert course.is_published is False


@pytest.mark.django_db
def test_student_cannot_see_course_under_unpublished_curriculum(student):
    curriculum = Curriculum.objects.create(
        code="CURR-TEST-3",
        title="Curriculum 3",
        is_published=False,
    )
    course = Course.objects.create(
        curriculum=curriculum,
        code="CRS-TEST-3",
        title="Course 3",
        is_published=True,  # Even if course flag is True, curriculum is unpublished
    )

    # ContentGateService should not return course to student
    visible_courses = ContentGateService.get_visible_courses(student)
    assert course not in visible_courses

    # Student cannot retrieve course details via API (should 404)
    client = APIClient()
    client.force_authenticate(user=student)
    response = client.get(f"/api/v1/lms/courses/{course.id}/")
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_only_system_admin_can_manage_and_publish_curricula_and_courses(system_admin, training_admin):
    client = APIClient()

    # Training admin cannot create curriculum
    client.force_authenticate(user=training_admin)
    create_curr_resp = client.post("/api/v1/lms/curricula/create/", {
        "code": "CURR-TA-TRY",
        "title": "Try Create Curr",
    })
    assert create_curr_resp.status_code == status.HTTP_403_FORBIDDEN

    # System admin can create curriculum
    client.force_authenticate(user=system_admin)
    create_curr_resp = client.post("/api/v1/lms/curricula/create/", {
        "code": "CURR-SA-OK",
        "title": "System Admin Curr",
    })
    assert create_curr_resp.status_code == status.HTTP_201_CREATED
    curr_id = create_curr_resp.data["data"]["id"]

    # Training admin cannot create course
    client.force_authenticate(user=training_admin)
    create_crs_resp = client.post("/api/v1/lms/courses/create/", {
        "curriculum": curr_id,
        "code": "CRS-TA-TRY",
        "title": "Try Create Course",
    })
    assert create_crs_resp.status_code == status.HTTP_403_FORBIDDEN

    # System admin can create course
    client.force_authenticate(user=system_admin)
    create_crs_resp = client.post("/api/v1/lms/courses/create/", {
        "curriculum": curr_id,
        "code": "CRS-SA-OK",
        "title": "System Admin Course",
    })
    assert create_crs_resp.status_code == status.HTTP_201_CREATED
    crs_id = create_crs_resp.data["data"]["id"]

    # Add a published module to the course so CourseService content checks pass
    course_obj = Course.objects.get(id=crs_id)
    Module.objects.create(
        course=course_obj,
        title="Module 1",
        is_published=True,
    )

    # System admin publishes curriculum first, then course
    pub_curr_resp = client.post(f"/api/v1/lms/curricula/{curr_id}/publish/")
    assert pub_curr_resp.status_code == status.HTTP_200_OK

    pub_crs_resp = client.post(f"/api/v1/lms/courses/{crs_id}/publish/")
    assert pub_crs_resp.status_code == status.HTTP_200_OK
