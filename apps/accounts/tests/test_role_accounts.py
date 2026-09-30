import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.constants import AccountStatus, UserRole
from apps.accounts.models import (
    EnterpriseProfile,
    ReviewerProfile,
    StudentProfile,
    TutorProfile,
)
from apps.accounts.services import (
    EnterpriseService,
    ReviewerService,
    StudentService,
    TutorService,
)

User = get_user_model()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def student_user(db):
    user = User.objects.create_user(
        phone_number="+250788111111",
        first_name="Jean",
        last_name="Mugisha",
        role=UserRole.STUDENT,
        status=AccountStatus.ACTIVE,
    )
    user.terms_of_service_accepted = True
    user.privacy_policy_accepted = True
    user.save()
    StudentProfile.objects.create(user=user, license_category="B")
    return user


@pytest.fixture
def tutor_user(db):
    user = User.objects.create_user(
        phone_number="+250788222222",
        first_name="Aline",
        last_name="Uwase",
        role=UserRole.TUTOR,
        status=AccountStatus.ACTIVE,
    )
    user.terms_of_service_accepted = True
    user.privacy_policy_accepted = True
    user.save()
    TutorService.get_or_create_profile(user)
    return user


@pytest.fixture
def enterprise_user(db):
    user = User.objects.create_user(
        phone_number="+250788333333",
        first_name="Director",
        last_name="Kigali",
        role=UserRole.ENTERPRISE_ADMIN,
        status=AccountStatus.ACTIVE,
        school_name="Kigali Modern Driving School",
        station_quota=25,
    )
    user.terms_of_service_accepted = True
    user.privacy_policy_accepted = True
    user.save()
    EnterpriseService.get_or_create_profile(user)
    return user


@pytest.fixture
def reviewer_user(db):
    user = User.objects.create_user(
        phone_number="+250788444444",
        first_name="Examiner",
        last_name="Inspector",
        role=UserRole.BOARD_REVIEWER,
        status=AccountStatus.ACTIVE,
    )
    user.terms_of_service_accepted = True
    user.privacy_policy_accepted = True
    user.save()
    ReviewerService.get_or_create_profile(user)
    return user


@pytest.mark.django_db
class TestStudentAccounts:
    def test_student_eligibility_endpoint(self, api_client, student_user):
        api_client.force_authenticate(user=student_user)
        response = api_client.get("/api/v1/auth/me/student-profile/eligibility/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data["data"]
        assert "eligible" in data
        assert "criteria" in data
        assert "tuition_paid" in data["criteria"]
        assert "attendance_rate" in data["criteria"]
        assert "module_completion" in data["criteria"]


@pytest.mark.django_db
class TestTutorAccounts:
    def test_tutor_dashboard_stats_endpoint(self, api_client, tutor_user, student_user):
        student_user.assigned_tutor = tutor_user
        student_user.save()

        api_client.force_authenticate(user=tutor_user)
        response = api_client.get("/api/v1/auth/tutor/stats/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data["data"]
        assert data["total_students"] == 1
        assert "tutor_code" in data

    def test_tutor_students_endpoint(self, api_client, tutor_user, student_user):
        student_user.assigned_tutor = tutor_user
        student_user.save()

        api_client.force_authenticate(user=tutor_user)
        response = api_client.get("/api/v1/auth/tutor/students/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data["data"]
        assert len(data) == 1
        assert data[0]["phone_number"] == student_user.phone_number


@pytest.mark.django_db
class TestEnterpriseAccounts:
    def test_enterprise_dashboard_stats_endpoint(self, api_client, enterprise_user):
        api_client.force_authenticate(user=enterprise_user)
        response = api_client.get("/api/v1/auth/enterprise/stats/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data["data"]
        assert data["concurrent_station_quota"] == 25
        assert data["school_name"] == "Kigali Modern Driving School"

    def test_enterprise_bulk_enroll(self, api_client, enterprise_user):
        api_client.force_authenticate(user=enterprise_user)
        payload = {
            "students": [
                {
                    "phone_number": "+250788555111",
                    "first_name": "Patrick",
                    "last_name": "Kamanzi",
                    "license_category": "B",
                },
                {
                    "phone_number": "+250788555222",
                    "first_name": "Diane",
                    "last_name": "Mutoni",
                    "license_category": "A",
                },
            ]
        }
        response = api_client.post("/api/v1/auth/enterprise/students/bulk/", data=payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["data"]["created_count"] == 2


@pytest.mark.django_db
class TestReviewerAccounts:
    def test_reviewer_dashboard_stats_endpoint(self, api_client, reviewer_user):
        api_client.force_authenticate(user=reviewer_user)
        response = api_client.get("/api/v1/auth/reviewer/stats/")
        assert response.status_code == status.HTTP_200_OK
        data = response.data["data"]
        assert "reviewer_code" in data
        assert "pending_queue_count" in data
