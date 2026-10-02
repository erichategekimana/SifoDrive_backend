import logging
from django.db.models import Q
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.mixins import SuccessResponseMixin
from apps.lms.models import HelpTicket, TicketRecipientRole, TicketStatus
from apps.lms.serializers import (
    HelpTicketCreateSerializer,
    HelpTicketResolveSerializer,
    HelpTicketSerializer,
)

logger = logging.getLogger(__name__)


class HelpTicketListCreateView(SuccessResponseMixin, generics.ListCreateAPIView):
    """
    GET  /api/v1/lms/support/tickets/ — List tickets relevant to user.
    POST /api/v1/lms/support/tickets/ — Submit a new help ticket to Tutor or Tech Team.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return HelpTicketCreateSerializer
        return HelpTicketSerializer

    def get_queryset(self):
        user = self.request.user
        if user.is_staff or getattr(user, "is_training_admin", False) or getattr(user, "is_system_admin", False):
            return HelpTicket.objects.all().select_related("user", "assigned_to")
        elif getattr(user, "is_tutor", False) or getattr(user, "role", "") == "TUTOR":
            # Tutors see tickets created by themselves or addressed to TUTOR
            return HelpTicket.objects.filter(
                Q(user=user) | Q(recipient_role=TicketRecipientRole.TUTOR) | Q(assigned_to=user)
            ).select_related("user", "assigned_to")
        # Students and guests see their own tickets
        return HelpTicket.objects.filter(user=user).select_related("user", "assigned_to")

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class HelpTicketDetailView(SuccessResponseMixin, generics.RetrieveUpdateAPIView):
    """
    GET   /api/v1/lms/support/tickets/<id>/ — Ticket detail.
    PATCH /api/v1/lms/support/tickets/<id>/ — Resolve or respond to ticket (Staff / Tutor).
    """
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "id"

    def get_serializer_class(self):
        if self.request.method in ["PUT", "PATCH"]:
            return HelpTicketResolveSerializer
        return HelpTicketSerializer

    def get_queryset(self):
        user = self.request.user
        if user.is_staff or getattr(user, "is_training_admin", False) or getattr(user, "is_system_admin", False):
            return HelpTicket.objects.all().select_related("user", "assigned_to")
        elif getattr(user, "is_tutor", False) or getattr(user, "role", "") == "TUTOR":
            return HelpTicket.objects.filter(
                Q(user=user) | Q(recipient_role=TicketRecipientRole.TUTOR) | Q(assigned_to=user)
            ).select_related("user", "assigned_to")
        return HelpTicket.objects.filter(user=user).select_related("user", "assigned_to")

    def patch(self, request, *args, **kwargs):
        ticket = self.get_object()
        serializer = HelpTicketResolveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ticket.mark_resolved(
            response_text=serializer.validated_data["response"],
            resolver=request.user,
        )
        if "status" in serializer.validated_data:
            ticket.status = serializer.validated_data["status"]
            ticket.save(update_fields=["status"])
        return self.success_response(
            data=HelpTicketSerializer(ticket).data,
            message="Ticket updated successfully.",
        )


class SupportAnnouncementsView(SuccessResponseMixin, APIView):
    """
    GET /api/v1/lms/support/announcements/
    Returns official tech support and training admin bulletins for students & tutors.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        bulletins = [
            {
                "id": "ann-001",
                "title": "Gahunda y'Amasomo y'Imbonankubone (Live Google Meet Sessions)",
                "author": "Training Admin & Instructors",
                "date": "2026-09-28",
                "category": "TRAINING",
                "content": (
                    "Amasomo yose y'amatsinda azajya aba kuwa mbere no kuwa gatatu guhera 18:00 kugeza 20:00. "
                    "Ihuza rya Google Meet riri mu gice cy'Amatsinda (Groups tab)."
                ),
                "is_pinned": True,
            },
            {
                "id": "ann-002",
                "title": "Kwandikisha Ikizamini cya Polisi kuri Irembo",
                "author": "Tech Support Team",
                "date": "2026-09-25",
                "category": "SYSTEM",
                "content": (
                    "Mbere yo gukoresha Irembo Concierge, banza wemeze ko wagejeje 85% mu bizamini by'igerageza "
                    "hano kuri Sifo Drive kugira ngo wemererwe."
                ),
                "is_pinned": False,
            },
            {
                "id": "ann-003",
                "title": "Ivugururwa rya Sisitemu (Maintenance Notice)",
                "author": "Platform Operations",
                "date": "2026-09-20",
                "category": "TECH",
                "content": (
                    "Urubuga ruzaba rurimo gukorerwa isuku kuwa gatandatu saa 02:00 kugeza 04:00 zo mu gitondo. "
                    "Nta kibazo kigaragara ku mwirondoro cyangwa amanota yanyu."
                ),
                "is_pinned": False,
            },
        ]
        return self.success_response(data=bulletins)
