import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.accounts.constants import UserRole
from apps.lms.models import HelpTicket, TicketCategory, TicketPriority, TicketRecipientRole, TicketStatus


@pytest.fixture
def student_user(db):
    return User.objects.create_user(
        phone_number="+250788111222",
        first_name="Jean",
        last_name="Mugisha",
        role=UserRole.STUDENT,
        password="TestPassword123!",
    )


@pytest.fixture
def tutor_user(db):
    return User.objects.create_user(
        phone_number="+250788333444",
        first_name="Claude",
        last_name="Kamanzi",
        role=UserRole.TUTOR,
        password="TestPassword123!",
    )


@pytest.fixture
def guest_user(db):
    return User.objects.create_user(
        phone_number="+250788555666",
        first_name="Alice",
        last_name="Uwase",
        role=UserRole.GUEST,
        password="TestPassword123!",
    )


@pytest.mark.django_db
def test_student_can_create_help_ticket(student_user):
    client = APIClient()
    client.force_authenticate(user=student_user)

    payload = {
        "recipient_role": TicketRecipientRole.TUTOR,
        "category": TicketCategory.CONTENT_INQUIRY,
        "subject": "Ikibazo ku cyapa cy'Umuvuduko ntarengwa",
        "message": "Ntabwo nasobanukiwe neza itandukaniro ry'icyapa cy'umuvuduko n'icyapa cy'umuvuduko muto usabwa.",
        "priority": TicketPriority.HIGH,
    }

    response = client.post("/api/v1/lms/support/tickets/", payload, format="json")
    assert response.status_code == status.HTTP_201_CREATED
    assert HelpTicket.objects.filter(user=student_user).count() == 1

    ticket = HelpTicket.objects.get(user=student_user)
    assert ticket.subject == payload["subject"]
    assert ticket.status == TicketStatus.OPEN


@pytest.mark.django_db
def test_tutor_can_view_and_resolve_ticket(student_user, tutor_user):
    ticket = HelpTicket.objects.create(
        user=student_user,
        recipient_role=TicketRecipientRole.TUTOR,
        category=TicketCategory.CONTENT_INQUIRY,
        subject="Ubufasha kuri Quiz 3",
        message="Mwaramutse mwarimu, ndifuza ubusobanuro ku kibazo cya 4.",
        status=TicketStatus.OPEN,
    )

    tutor_client = APIClient()
    tutor_client.force_authenticate(user=tutor_user)

    # Tutor lists tickets
    list_res = tutor_client.get("/api/v1/lms/support/tickets/")
    assert list_res.status_code == status.HTTP_200_OK
    items = list_res.data.get("results") or list_res.data.get("data") or []
    assert len(items) >= 1

    # Tutor resolves ticket
    patch_res = tutor_client.patch(
        f"/api/v1/lms/support/tickets/{ticket.id}/",
        {"response": "Mugisha, ikibazo cya 4 kirebana n'icyapa kiburira. Reba ku rupapuro rwa 12.", "status": TicketStatus.RESOLVED},
        format="json",
    )
    assert patch_res.status_code == status.HTTP_200_OK
    ticket.refresh_from_db()
    assert ticket.status == TicketStatus.RESOLVED
    assert ticket.assigned_to == tutor_user
    assert "Mugisha" in ticket.response



@pytest.mark.django_db
def test_support_announcements_empty_when_no_records(student_user):
    client = APIClient()
    client.force_authenticate(user=student_user)
    res = client.get("/api/v1/lms/support/announcements/")
    assert res.status_code == status.HTTP_200_OK
    assert res.data["data"] == []


@pytest.mark.django_db
def test_tutor_can_post_and_student_views_cohort_announcements(tutor_user, student_user):
    from apps.live_classes.models import Cohort
    from apps.lms.models import Course, Curriculum, AnnouncementTargetType

    curriculum = Curriculum.objects.create(title="Theory", code="THEORY-01")
    course = Course.objects.create(title="Road Signs", code="SIGNS-01", curriculum=curriculum)
    cohort_a = Cohort.objects.create(name="Cohort Morning", code="COHORT-MORN", start_date="2026-01-01")
    cohort_b = Cohort.objects.create(name="Cohort Evening", code="COHORT-EVE", start_date="2026-01-01")

    cohort_a.assigned_tutors.add(tutor_user)
    cohort_b.assigned_tutors.add(tutor_user)
    cohort_a.students.add(student_user)

    # Other student in cohort B
    other_student = User.objects.create_user(
        phone_number="+250788777888",
        first_name="David",
        last_name="Rutayisire",
        role=UserRole.STUDENT,
        password="TestPassword123!",
    )
    cohort_b.students.add(other_student)

    tutor_client = APIClient()
    tutor_client.force_authenticate(user=tutor_user)

    # 1. Tutor posts announcement for SINGLE_COHORT (Cohort A only)
    post_res = tutor_client.post(
        "/api/v1/lms/support/announcements/",
        {
            "course_id": str(course.id),
            "title": "Morning Cohort Special Review",
            "content": "Special Q&A session tomorrow morning at 09:00.",
            "target_type": AnnouncementTargetType.SINGLE_COHORT,
            "cohort_id": str(cohort_a.id),
        },
        format="json",
    )
    assert post_res.status_code == status.HTTP_201_CREATED
    ann_id = post_res.data["data"]["id"]
    assert post_res.data["data"]["target_type"] == "SINGLE_COHORT"
    assert post_res.data["data"]["cohort_name"] == "Cohort Morning"

    # Student Jean in Cohort A can see it
    student_client = APIClient()
    student_client.force_authenticate(user=student_user)
    res_a = student_client.get(f"/api/v1/lms/support/announcements/?course_id={course.id}")
    assert res_a.status_code == status.HTTP_200_OK
    assert len(res_a.data["data"]) == 1
    assert res_a.data["data"][0]["title"] == "Morning Cohort Special Review"

    # Other student David in Cohort B CANNOT see it
    other_client = APIClient()
    other_client.force_authenticate(user=other_student)
    res_b = other_client.get(f"/api/v1/lms/support/announcements/?course_id={course.id}")
    assert res_b.status_code == status.HTTP_200_OK
    assert len(res_b.data["data"]) == 0

    # 2. Tutor posts announcement for ALL_ASSIGNED_COHORTS
    post_all_res = tutor_client.post(
        "/api/v1/lms/support/announcements/",
        {
            "course_id": str(course.id),
            "title": "All Cohorts: Highway Code Update",
            "content": "Please read chapter 4 regarding right of way changes.",
            "target_type": AnnouncementTargetType.ALL_ASSIGNED_COHORTS,
        },
        format="json",
    )
    assert post_all_res.status_code == status.HTTP_201_CREATED
    assert post_all_res.data["data"]["target_type"] == "ALL_ASSIGNED_COHORTS"

    # Both students now see the broadcast announcement!
    res_a_after = student_client.get(f"/api/v1/lms/support/announcements/?course_id={course.id}")
    assert len(res_a_after.data["data"]) == 2

    res_b_after = other_client.get(f"/api/v1/lms/support/announcements/?course_id={course.id}")
    assert len(res_b_after.data["data"]) == 1
    assert res_b_after.data["data"][0]["title"] == "All Cohorts: Highway Code Update"

    # 3. Tutor can delete announcement
    del_res = tutor_client.delete(f"/api/v1/lms/support/announcements/{ann_id}/")
    assert del_res.status_code == status.HTTP_200_OK

    res_a_final = student_client.get(f"/api/v1/lms/support/announcements/?course_id={course.id}")
    assert len(res_a_final.data["data"]) == 1

