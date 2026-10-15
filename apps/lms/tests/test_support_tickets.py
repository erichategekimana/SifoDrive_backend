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


@pytest.fixture
def system_admin_user(db):
    return User.objects.create_user(
        phone_number="+250788111999",
        first_name="Super",
        last_name="Admin",
        role=UserRole.SYSTEM_ADMIN,
        is_superuser=True,
        password="TestPassword123!",
    )


@pytest.mark.django_db
def test_system_admin_can_post_announcements_and_training_admin_forbidden(
    system_admin_user, student_user, training_admin_user
):
    from apps.lms.models import AnnouncementTargetType

    # 1. Training admin attempts to post a bulletin -> MUST BE FORBIDDEN (403)
    train_client = APIClient()
    train_client.force_authenticate(user=training_admin_user)
    forbidden_res = train_client.post(
        "/api/v1/lms/support/announcements/",
        {
            "title": "Training Admin Attempt",
            "content": "This should not be allowed.",
            "target_type": AnnouncementTargetType.PLATFORM_WIDE,
            "category": "PLATFORM_UPDATE",
        },
        format="json",
    )
    assert forbidden_res.status_code == status.HTTP_403_FORBIDDEN

    # 2. System Admin creates platform update & help announcement -> SUCCEEDS (201)
    admin_client = APIClient()
    admin_client.force_authenticate(user=system_admin_user)
    post_res = admin_client.post(
        "/api/v1/lms/support/announcements/",
        {
            "title": "Platform Maintenance & Feature Release",
            "content": "Scheduled maintenance on Saturday 22:00 UTC. New calendar features released.",
            "target_type": AnnouncementTargetType.PLATFORM_WIDE,
            "category": "PLATFORM_UPDATE",
            "is_pinned": True,
        },
        format="json",
    )
    assert post_res.status_code == status.HTTP_201_CREATED
    ann_id = post_res.data["data"]["id"]
    assert post_res.data["data"]["title"] == "Platform Maintenance & Feature Release"
    assert post_res.data["data"]["category"] == "PLATFORM_UPDATE"
    assert post_res.data["data"]["is_pinned"] is True

    # 3. Student can view this platform-wide announcement in Support tab
    student_client = APIClient()
    student_client.force_authenticate(user=student_user)
    get_res = student_client.get("/api/v1/lms/support/announcements/")
    assert get_res.status_code == status.HTTP_200_OK
    assert len(get_res.data["data"]) == 1
    assert get_res.data["data"][0]["title"] == "Platform Maintenance & Feature Release"
    assert get_res.data["data"][0]["category"] == "PLATFORM_UPDATE"

    # 4. System Admin can delete the announcement
    del_res = admin_client.delete(f"/api/v1/lms/support/announcements/{ann_id}/")
    assert del_res.status_code == status.HTTP_200_OK

    # 5. Announcement is no longer visible
    get_res_after = student_client.get("/api/v1/lms/support/announcements/")
    assert len(get_res_after.data["data"]) == 0


@pytest.fixture
def training_admin_user(db):
    return User.objects.create_user(
        phone_number="+250788999000",
        first_name="Admin",
        last_name="Training",
        role=UserRole.TRAINING_ADMIN,
        password="TestPassword123!",
    )


@pytest.mark.django_db
def test_training_admin_collects_forwards_and_student_submits_feedback(
    student_user, tutor_user, training_admin_user
):
    # 1. Student creates ticket
    student_client = APIClient()
    student_client.force_authenticate(user=student_user)

    create_res = student_client.post(
        "/api/v1/lms/support/tickets/",
        {
            "recipient_role": TicketRecipientRole.TECH_SUPPORT,
            "category": TicketCategory.TECHNICAL_ISSUE,
            "subject": "Platform login error",
            "message": "I cannot load lesson 3 video stream on mobile.",
            "priority": TicketPriority.URGENT,
        },
        format="json",
    )
    assert create_res.status_code == status.HTTP_201_CREATED
    ticket_id = create_res.data.get("id") or (create_res.data.get("data") or {}).get("id")

    # 2. Training Admin collects and sees all tickets
    admin_client = APIClient()
    admin_client.force_authenticate(user=training_admin_user)

    admin_list = admin_client.get("/api/v1/lms/support/tickets/")
    assert admin_list.status_code == status.HTTP_200_OK
    tickets = admin_list.data.get("data") or admin_list.data.get("results") or []
    found = [t for t in tickets if str(t["id"]) == str(ticket_id)]
    assert len(found) == 1
    assert found[0]["status"] == TicketStatus.OPEN

    # 2b. Training Admin queries assignable users
    assignable_res = admin_client.get("/api/v1/lms/support/assignable-users/")
    assert assignable_res.status_code == status.HTTP_200_OK
    assignable_users = assignable_res.data.get("data", [])
    assert any(u["id"] == str(tutor_user.id) for u in assignable_users)

    # 3. Training Admin forwards ticket to tutor
    forward_res = admin_client.post(
        f"/api/v1/lms/support/tickets/{ticket_id}/forward/",
        {
            "assigned_to": str(tutor_user.id),
            "internal_notes": "Please check student video permission on cohort 1.",
        },
        format="json",
    )
    assert forward_res.status_code == status.HTTP_200_OK
    ticket = HelpTicket.objects.get(id=ticket_id)
    assert ticket.assigned_to == tutor_user
    assert ticket.forwarded_by == training_admin_user
    assert ticket.status == TicketStatus.IN_PROGRESS
    assert "Please check student video permission" in ticket.internal_notes

    # 4. Training Admin updates ticket status to RESOLVED
    status_res = admin_client.patch(
        f"/api/v1/lms/support/tickets/{ticket_id}/status/",
        {
            "status": TicketStatus.RESOLVED,
            "response": "The video stream encoding has been repaired. Please refresh your browser.",
        },
        format="json",
    )
    assert status_res.status_code == status.HTTP_200_OK
    ticket.refresh_from_db()
    assert ticket.status == TicketStatus.RESOLVED
    assert "repaired" in ticket.response

    # 5. Student provides feedback (Like & Solved)
    feedback_res = student_client.post(
        f"/api/v1/lms/support/tickets/{ticket_id}/feedback/",
        {
            "rating": "LIKE",
            "resolution": "SOLVED",
            "notes": "Thank you, it works quickly now!",
        },
        format="json",
    )
    assert feedback_res.status_code == status.HTTP_200_OK
    ticket.refresh_from_db()
    assert ticket.feedback_rating == "LIKE"
    assert ticket.feedback_resolution == "SOLVED"
    assert "works quickly" in ticket.feedback_notes
    assert ticket.feedback_submitted_at is not None

    # 6. If student reports UNSOLVED, ticket status is marked REOPENED
    feedback_unsolved = student_client.post(
        f"/api/v1/lms/support/tickets/{ticket_id}/feedback/",
        {
            "rating": "DISLIKE",
            "resolution": "UNSOLVED",
            "notes": "Actually video 4 still stops at minute 2.",
        },
        format="json",
    )
    assert feedback_unsolved.status_code == status.HTTP_200_OK
    ticket.refresh_from_db()
    assert ticket.status == TicketStatus.REOPENED
    assert ticket.feedback_resolution == "UNSOLVED"


