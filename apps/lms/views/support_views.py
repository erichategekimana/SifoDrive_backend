import logging
from django.db.models import Q
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.mixins import SuccessResponseMixin
from apps.lms.models import (
    Announcement,
    AnnouncementTargetType,
    HelpTicket,
    TicketRecipientRole,
    TicketStatus,
)
from apps.lms.serializers import (
    AnnouncementCreateSerializer,
    AnnouncementSerializer,
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
    GET  /api/v1/lms/support/announcements/
    Returns real, persisted announcements filtered by course and cohort visibility.
    - Students see announcements targeted to their enrolled cohorts, or broadcast to all cohorts of their tutors, or course-wide.
    - Tutors see announcements they authored, announcements targeting their assigned cohorts, or course-wide.
    
    POST /api/v1/lms/support/announcements/
    Allows tutors and training administrators to post an announcement targeted to:
    - One specific cohort (SINGLE_COHORT)
    - All cohorts assigned to the tutor (ALL_ASSIGNED_COHORTS)
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user
        course_id = request.query_params.get("course_id")
        cohort_id = request.query_params.get("cohort_id")

        qs = Announcement.objects.filter(is_deleted=False).select_related("author", "course", "cohort").prefetch_related("cohorts")

        if course_id:
            qs = qs.filter(course_id=course_id)

        is_admin = (
            user.is_staff
            or getattr(user, "is_training_admin", False)
            or getattr(user, "is_system_admin", False)
            or getattr(user, "role", "") in ["SYSTEM_ADMIN", "TRAINING_ADMIN"]
        )

        if not is_admin:
            is_tutor = getattr(user, "is_tutor", False) or getattr(user, "role", "") == "TUTOR"
            if is_tutor:
                assigned_cohort_ids = list(user.assigned_cohorts.filter(is_deleted=False).values_list("id", flat=True))
                cond = (
                    Q(author=user)
                    | Q(cohort_id__in=assigned_cohort_ids)
                    | Q(cohorts__in=assigned_cohort_ids)
                    | Q(target_type=AnnouncementTargetType.COURSE_WIDE)
                )
                qs = qs.filter(cond)

                if cohort_id:
                    qs = qs.filter(
                        Q(cohort_id=cohort_id)
                        | (Q(target_type=AnnouncementTargetType.ALL_ASSIGNED_COHORTS) & Q(cohorts__id=cohort_id))
                        | (Q(target_type=AnnouncementTargetType.ALL_ASSIGNED_COHORTS) & Q(author__assigned_cohorts__id=cohort_id))
                    )
            else:
                # Student or Guest
                enrolled_cohort_ids = list(user.enrolled_cohorts.filter(is_deleted=False).values_list("id", flat=True))
                cond = (
                    Q(cohort_id__in=enrolled_cohort_ids)
                    | Q(cohorts__in=enrolled_cohort_ids)
                    | (Q(target_type=AnnouncementTargetType.ALL_ASSIGNED_COHORTS) & Q(author__assigned_cohorts__in=enrolled_cohort_ids))
                    | Q(target_type=AnnouncementTargetType.COURSE_WIDE)
                )
                qs = qs.filter(cond)
        else:
            if cohort_id:
                qs = qs.filter(Q(cohort_id=cohort_id) | Q(cohorts__id=cohort_id))

        qs = qs.distinct().order_by("-is_pinned", "-created_at")
        serializer = AnnouncementSerializer(qs, many=True)
        return self.success_response(data=serializer.data)

    def post(self, request, *args, **kwargs):
        user = request.user
        can_post = (
            user.is_staff
            or getattr(user, "is_training_admin", False)
            or getattr(user, "is_system_admin", False)
            or getattr(user, "is_tutor", False)
            or getattr(user, "role", "") in ["TUTOR", "TRAINING_ADMIN", "SYSTEM_ADMIN"]
        )
        if not can_post:
            return Response(
                {"success": False, "message": "Only tutors and administrators may post announcements."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = AnnouncementCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        announcement = serializer.save()
        return self.success_response(
            data=AnnouncementSerializer(announcement).data,
            message="Announcement posted successfully.",
            status_code=status.HTTP_201_CREATED,
        )


class SupportAnnouncementDetailView(SuccessResponseMixin, APIView):
    """
    DELETE /api/v1/lms/support/announcements/<uuid:pk>/
    Delete an announcement. Only author or administrator can delete.
    """
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, pk, *args, **kwargs):
        announcement = Announcement.objects.filter(id=pk, is_deleted=False).first()
        if not announcement:
            return Response(
                {"success": False, "message": "Announcement not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        is_admin = (
            request.user.is_staff
            or getattr(request.user, "is_training_admin", False)
            or getattr(request.user, "is_system_admin", False)
            or getattr(request.user, "role", "") in ["SYSTEM_ADMIN", "TRAINING_ADMIN"]
        )
        if announcement.author_id != request.user.id and not is_admin:
            return Response(
                {"success": False, "message": "You can only delete your own announcements."},
                status=status.HTTP_403_FORBIDDEN,
            )

        announcement.is_deleted = True
        announcement.save(update_fields=["is_deleted", "updated_at"])
        return self.success_response(message="Announcement deleted successfully.")
