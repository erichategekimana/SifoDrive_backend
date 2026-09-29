import logging
from django.db import models
from rest_framework import generics, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.booking.models import BookingApplication, BookingState
from apps.booking.serializers import (
    AdminBookingCompleteSerializer,
    AdminBookingStatusUpdateSerializer,
    BookingApplicationCreateSerializer,
    BookingApplicationDetailSerializer,
    BookingApplicationListSerializer,
)
from apps.booking.services import BookingService
from apps.core.mixins import SuccessResponseMixin
from apps.core.pagination import StandardResultsPagination
from apps.core.permissions import IsAdminLevel

logger = logging.getLogger("apps.booking.views.booking_views")


class BookingApplicationCreateView(SuccessResponseMixin, APIView):
    """
    Submit a driving test booking application.
    Requires authentication (Guest or Student).
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = BookingApplicationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        booking = BookingService.apply_for_booking(
            applicant=request.user,
            first_name=data["first_name"],
            last_name=data["last_name"],
            phone_number=data["phone_number"],
            national_id=data["national_id"],
            date_of_birth=data["date_of_birth"],
            license_category=data["license_category"],
            preferred_district=data["preferred_district"],
            working_site=data.get("working_site"),
            partner_teacher_id=data.get("partner_teacher_id"),
            request=request,
        )

        out_serializer = BookingApplicationDetailSerializer(booking, context={"request": request})
        return self.created_response(
            data=out_serializer.data,
            message=f"Booking application {booking.ticket_number} submitted successfully.",
        )


class MyBookingsListView(SuccessResponseMixin, generics.ListAPIView):
    """
    List driving test booking applications submitted by the current user.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = BookingApplicationListSerializer
    pagination_class = StandardResultsPagination

    def get_queryset(self):
        return BookingApplication.objects.filter(applicant=self.request.user).order_by("-submitted_at")


class BookingDetailView(SuccessResponseMixin, generics.RetrieveAPIView):
    """
    Retrieve full details of a booking application.
    Restricted to applicant or authorized administrative staff.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = BookingApplicationDetailSerializer

    def get_queryset(self):
        user = self.request.user
        if user.is_staff or getattr(user, "role", None) in ("SYSTEM_ADMIN", "ENTERPRISE_ADMIN", "BOARD_REVIEWER"):
            return BookingApplication.objects.all()
        return BookingApplication.objects.filter(applicant=user)


class BookingCancelView(SuccessResponseMixin, APIView):
    """
    Cancel an uncompleted booking application.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk, *args, **kwargs):
        reason = request.data.get("reason", "")
        booking = BookingService.cancel_booking(
            booking_id=str(pk),
            user=request.user,
            reason=reason,
            request=request,
        )
        serializer = BookingApplicationDetailSerializer(booking, context={"request": request})
        return self.success_response(
            data=serializer.data,
            message=f"Booking {booking.ticket_number} has been cancelled.",
        )


class AdminBookingOrderListView(SuccessResponseMixin, generics.ListAPIView):
    """
    Admin queue: list all booking orders with advanced filtering and search.
    Restricted to Admin Level (Enterprise Admin, Board Reviewer, System Admin).
    """
    permission_classes = [IsAuthenticated, IsAdminLevel]
    serializer_class = BookingApplicationListSerializer
    pagination_class = StandardResultsPagination

    def get_queryset(self):
        qs = BookingApplication.objects.all().order_by("-submitted_at")

        # Filters
        state_param = self.request.query_params.get("state")
        if state_param:
            qs = qs.filter(state=state_param.upper())

        cat_param = self.request.query_params.get("category")
        if cat_param:
            qs = qs.filter(license_category=cat_param.upper())

        district_param = self.request.query_params.get("district")
        if district_param:
            qs = qs.filter(preferred_district__iexact=district_param)

        teacher_param = self.request.query_params.get("teacher_id")
        if teacher_param:
            qs = qs.filter(partner_teacher_id=teacher_param)

        # Search
        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(
                models.Q(ticket_number__icontains=search)
                | models.Q(phone_number__icontains=search)
                | models.Q(first_name__icontains=search)
                | models.Q(last_name__icontains=search)
                | models.Q(irembo_billing_number__icontains=search)
            )

        return qs


class AdminBookingOrderDetailView(SuccessResponseMixin, generics.RetrieveAPIView):
    """
    Admin detail view for a booking application. Exposes decrypted NID to authorized admin.
    """
    permission_classes = [IsAuthenticated, IsAdminLevel]
    serializer_class = BookingApplicationDetailSerializer
    queryset = BookingApplication.objects.all()


class AdminBookingAssignAgentView(SuccessResponseMixin, APIView):
    """
    Assign an agent/admin to process the booking. Transitions state to PROCESSING.
    """
    permission_classes = [IsAuthenticated, IsAdminLevel]

    def post(self, request, pk, *args, **kwargs):
        target_agent = request.user
        agent_id = request.data.get("agent_id")
        if agent_id and request.user.role == "SYSTEM_ADMIN":
            from apps.accounts.models import User
            try:
                target_agent = User.objects.get(id=agent_id)
            except User.DoesNotExist:
                return self.error_response(
                    code="NOT_FOUND",
                    message="Target agent user not found.",
                    status_code=status.HTTP_404_NOT_FOUND,
                )

        booking = BookingService.assign_agent(
            booking_id=str(pk),
            agent=target_agent,
            request=request,
        )
        serializer = BookingApplicationDetailSerializer(booking, context={"request": request})
        return self.success_response(
            data=serializer.data,
            message=f"Booking {booking.ticket_number} assigned to {target_agent.get_full_name() or target_agent.phone_number}.",
        )


class AdminBookingStatusUpdateView(SuccessResponseMixin, APIView):
    """
    Update booking state (e.g. SLOTS_UNAVAILABLE, CANCELLED).
    """
    permission_classes = [IsAuthenticated, IsAdminLevel]

    def patch(self, request, pk, *args, **kwargs):
        serializer = AdminBookingStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        new_state = serializer.validated_data["state"]
        notes = serializer.validated_data.get("agent_notes", "")

        if new_state == BookingState.SLOTS_UNAVAILABLE:
            booking = BookingService.mark_slots_unavailable(
                booking_id=str(pk),
                agent=request.user,
                agent_notes=notes,
                request=request,
            )
        elif new_state == BookingState.CANCELLED:
            booking = BookingService.cancel_booking(
                booking_id=str(pk),
                user=request.user,
                reason=notes,
                request=request,
            )
        else:
            booking = BookingApplication.objects.get(id=pk)
            booking.state = new_state
            if notes:
                booking.agent_notes = notes
            booking.save(update_fields=["state", "agent_notes", "updated_at"])

        out_serializer = BookingApplicationDetailSerializer(booking, context={"request": request})
        return self.success_response(
            data=out_serializer.data,
            message=f"Booking {booking.ticket_number} status updated to {booking.state}.",
        )


class AdminBookingCompleteView(SuccessResponseMixin, APIView):
    """
    Complete booking: attach Irembo billing number and notify applicant.
    Supports multipart form for confirmation PDF upload.
    """
    permission_classes = [IsAuthenticated, IsAdminLevel]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request, pk, *args, **kwargs):
        serializer = AdminBookingCompleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        booking = BookingService.complete_booking(
            booking_id=str(pk),
            agent=request.user,
            irembo_billing_number=data["irembo_billing_number"],
            test_date=data.get("confirmed_test_date"),
            test_time=data.get("confirmed_test_time"),
            venue=data.get("confirmed_venue", ""),
            confirmation_pdf=data.get("confirmation_pdf"),
            agent_notes=data.get("agent_notes", ""),
            irembo_application_number=data.get("irembo_application_number", ""),
            request=request,
        )

        out_serializer = BookingApplicationDetailSerializer(booking, context={"request": request})
        return self.success_response(
            data=out_serializer.data,
            message=f"Booking {booking.ticket_number} completed with Irembo billing number {booking.irembo_billing_number}.",
        )
