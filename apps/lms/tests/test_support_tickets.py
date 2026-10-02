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
def test_support_announcements_endpoint(student_user):
    client = APIClient()
    client.force_authenticate(user=student_user)
    res = client.get("/api/v1/lms/support/announcements/")
    assert res.status_code == status.HTTP_200_OK
    assert len(res.data["data"]) >= 1
