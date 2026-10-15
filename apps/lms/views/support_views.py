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
    HelpTicketFeedbackSerializer,
    HelpTicketForwardSerializer,
    HelpTicketResolveSerializer,
    HelpTicketSerializer,
    HelpTicketStatusUpdateSerializer,
    SupportAssignableUserSerializer,
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
        is_admin = (
            user.is_staff
            or getattr(user, "is_training_admin", False)
            or getattr(user, "is_system_admin", False)
            or getattr(user, "role", "") in ["TRAINING_ADMIN", "SYSTEM_ADMIN"]
        )
        if is_admin:
            return HelpTicket.objects.all().select_related("user", "assigned_to", "forwarded_by")
        elif getattr(user, "is_tutor", False) or getattr(user, "role", "") == "TUTOR":
            # Tutors see tickets created by themselves or addressed to TUTOR or assigned to them
            return HelpTicket.objects.filter(
                Q(user=user) | Q(recipient_role=TicketRecipientRole.TUTOR) | Q(assigned_to=user)
            ).select_related("user", "assigned_to", "forwarded_by")
        # Students and guests see their own tickets
        return HelpTicket.objects.filter(user=user).select_related("user", "assigned_to", "forwarded_by")

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
        is_admin = (
            user.is_staff
            or getattr(user, "is_training_admin", False)
            or getattr(user, "is_system_admin", False)
            or getattr(user, "role", "") in ["TRAINING_ADMIN", "SYSTEM_ADMIN"]
        )
        if is_admin:
            return HelpTicket.objects.all().select_related("user", "assigned_to", "forwarded_by")
        elif getattr(user, "is_tutor", False) or getattr(user, "role", "") == "TUTOR":
            return HelpTicket.objects.filter(
                Q(user=user) | Q(recipient_role=TicketRecipientRole.TUTOR) | Q(assigned_to=user)
            ).select_related("user", "assigned_to", "forwarded_by")
        return HelpTicket.objects.filter(user=user).select_related("user", "assigned_to", "forwarded_by")

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


class HelpTicketForwardView(SuccessResponseMixin, APIView):
    """
    POST /api/v1/lms/support/tickets/<id>/forward/
    Allows Training Admin or Staff to forward a ticket to a respective user (tutor, instructor, tech support).
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, id, *args, **kwargs):
        user = request.user
        is_admin = (
            user.is_staff
            or getattr(user, "is_training_admin", False)
            or getattr(user, "is_system_admin", False)
            or getattr(user, "role", "") in ["TRAINING_ADMIN", "SYSTEM_ADMIN"]
        )
        if not is_admin:
            return Response(
                {"success": False, "message": "Only training administrators or staff can forward tickets."},
                status=status.HTTP_403_FORBIDDEN,
            )

        ticket = HelpTicket.objects.filter(id=id).first()
        if not ticket:
            return Response({"success": False, "message": "Ticket not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = HelpTicketForwardSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        from apps.accounts.models import User
        assignee = User.objects.filter(id=serializer.validated_data["assigned_to"]).first()
        if not assignee:
            return Response({"success": False, "message": "Assignee user not found."}, status=status.HTTP_404_NOT_FOUND)

        ticket.forward_to(
            assignee=assignee,
            forwarded_by=user,
            internal_notes=serializer.validated_data.get("internal_notes", ""),
        )
        return self.success_response(
            data=HelpTicketSerializer(ticket).data,
            message=f"Ticket forwarded to {assignee.full_name or assignee.phone_number} successfully.",
        )


class HelpTicketStatusUpdateView(SuccessResponseMixin, APIView):
    """
    PATCH /api/v1/lms/support/tickets/<id>/status/
    Updates ticket status, response, internal notes, or assigned staff.
    """
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, id, *args, **kwargs):
        ticket = HelpTicket.objects.filter(id=id).first()
        if not ticket:
            return Response({"success": False, "message": "Ticket not found."}, status=status.HTTP_404_NOT_FOUND)

        user = request.user
        is_admin = (
            user.is_staff
            or getattr(user, "is_training_admin", False)
            or getattr(user, "is_system_admin", False)
            or getattr(user, "role", "") in ["TRAINING_ADMIN", "SYSTEM_ADMIN"]
        )
        is_assignee = ticket.assigned_to_id == user.id
        is_tutor = getattr(user, "is_tutor", False) or getattr(user, "role", "") == "TUTOR"
        if not is_admin and not is_assignee and not (is_tutor and ticket.recipient_role == TicketRecipientRole.TUTOR):
            return Response(
                {"success": False, "message": "You are not authorized to update this ticket's status."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = HelpTicketStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        assignee = None
        if data.get("assigned_to"):
            from apps.accounts.models import User
            assignee = User.objects.filter(id=data["assigned_to"]).first()

        ticket.update_status(
            new_status=data["status"],
            response_text=data.get("response", ""),
            updater=assignee or user,
            internal_notes=data.get("internal_notes", ""),
        )
        return self.success_response(
            data=HelpTicketSerializer(ticket).data,
            message="Ticket status updated successfully.",
        )


class HelpTicketFeedbackView(SuccessResponseMixin, APIView):
    """
    POST /api/v1/lms/support/tickets/<id>/feedback/
    Allows the student who submitted the ticket to rate the resolution (Like/Dislike, Solved/Unsolved).
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, id, *args, **kwargs):
        ticket = HelpTicket.objects.filter(id=id).first()
        if not ticket:
            return Response({"success": False, "message": "Ticket not found."}, status=status.HTTP_404_NOT_FOUND)

        if ticket.user_id != request.user.id and not request.user.is_superuser:
            return Response(
                {"success": False, "message": "Only the student who submitted this ticket can provide feedback."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if ticket.status not in [TicketStatus.RESOLVED, TicketStatus.CLOSED, TicketStatus.REOPENED]:
            return Response(
                {"success": False, "message": "Feedback can only be submitted for resolved or closed tickets."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = HelpTicketFeedbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ticket.submit_feedback(
            rating=serializer.validated_data["rating"],
            resolution=serializer.validated_data["resolution"],
            notes=serializer.validated_data.get("notes", ""),
        )
        return self.success_response(
            data=HelpTicketSerializer(ticket).data,
            message="Thank you! Your feedback has been recorded.",
        )


class SupportAssignableUsersView(SuccessResponseMixin, APIView):
    """
    GET /api/v1/lms/support/assignable-users/
    Returns staff, training admins, tutors, and technical support users that tickets can be forwarded to.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        from apps.accounts.models import User
        from apps.accounts.constants import UserRole

        users = (
            User.objects.filter(
                is_active=True,
            )
            .filter(
                Q(is_staff=True)
                | Q(role__in=[UserRole.TUTOR, UserRole.TRAINING_ADMIN, UserRole.SYSTEM_ADMIN])
            )
            .order_by("first_name", "last_name")
        )

        data = [
            {
                "id": str(u.id),
                "full_name": u.full_name or f"{u.first_name} {u.last_name}".strip() or u.phone_number,
                "phone_number": u.phone_number,
                "role": u.role,
                "email": u.email or "",
            }
            for u in users
        ]
        return self.success_response(data=data)


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
                    | Q(target_type=AnnouncementTargetType.PLATFORM_WIDE)
                    | Q(author__role="SYSTEM_ADMIN")
                    | Q(author__is_superuser=True)
                )
                qs = qs.filter(cond)

                if cohort_id:
                    qs = qs.filter(
                        Q(cohort_id=cohort_id)
                        | (Q(target_type=AnnouncementTargetType.ALL_ASSIGNED_COHORTS) & Q(cohorts__id=cohort_id))
                        | (Q(target_type=AnnouncementTargetType.ALL_ASSIGNED_COHORTS) & Q(author__assigned_cohorts__id=cohort_id))
                        | Q(target_type=AnnouncementTargetType.PLATFORM_WIDE)
                        | Q(author__role="SYSTEM_ADMIN")
                    )
            else:
                # Student, Guest, Agent, Board Reviewer, Enterprise Admin
                enrolled_cohort_ids = list(user.enrolled_cohorts.filter(is_deleted=False).values_list("id", flat=True)) if hasattr(user, "enrolled_cohorts") else []
                cond = (
                    Q(cohort_id__in=enrolled_cohort_ids)
                    | Q(cohorts__in=enrolled_cohort_ids)
                    | (Q(target_type=AnnouncementTargetType.ALL_ASSIGNED_COHORTS) & Q(author__assigned_cohorts__in=enrolled_cohort_ids))
                    | Q(target_type=AnnouncementTargetType.COURSE_WIDE)
                    | Q(target_type=AnnouncementTargetType.PLATFORM_WIDE)
                    | Q(author__role="SYSTEM_ADMIN")
                    | Q(author__is_superuser=True)
                )
                qs = qs.filter(cond)
        else:
            if cohort_id:
                qs = qs.filter(
                    Q(cohort_id=cohort_id)
                    | Q(cohorts__id=cohort_id)
                    | Q(target_type=AnnouncementTargetType.PLATFORM_WIDE)
                    | Q(author__role="SYSTEM_ADMIN")
                )

        qs = qs.distinct().order_by("-is_pinned", "-created_at")
        serializer = AnnouncementSerializer(qs, many=True)
        return self.success_response(data=serializer.data)

    def post(self, request, *args, **kwargs):
        user = request.user
        is_system_admin = (
            user.is_superuser
            or getattr(user, "is_system_admin", False)
            or getattr(user, "role", "") == "SYSTEM_ADMIN"
        )
        if not is_system_admin:
            return Response(
                {
                    "success": False,
                    "message": "Only System Administrators are permitted to create and publish help support messages, platform updates, and announcements. Training Administrators are not authorized to perform this action.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = AnnouncementCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        announcement = serializer.save()
        return self.success_response(
            data=AnnouncementSerializer(announcement).data,
            message="Support bulletin / announcement published successfully.",
            status_code=status.HTTP_201_CREATED,
        )


class SupportAnnouncementDetailView(SuccessResponseMixin, APIView):
    """
    DELETE /api/v1/lms/support/announcements/<uuid:pk>/
    Delete an announcement. Only System Administrators or original author can delete.
    """
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, pk, *args, **kwargs):
        announcement = Announcement.objects.filter(id=pk, is_deleted=False).first()
        if not announcement:
            return Response(
                {"success": False, "message": "Announcement not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        is_system_admin = (
            request.user.is_superuser
            or getattr(request.user, "is_system_admin", False)
            or getattr(request.user, "role", "") == "SYSTEM_ADMIN"
        )
        if announcement.author_id != request.user.id and not is_system_admin:
            return Response(
                {"success": False, "message": "Only System Administrators can delete support announcements."},
                status=status.HTTP_403_FORBIDDEN,
            )

        announcement.is_deleted = True
        announcement.save(update_fields=["is_deleted", "updated_at"])
        return self.success_response(message="Announcement deleted successfully.")
