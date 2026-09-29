"""
apps/accounts/views/agent_views.py
==================================
API views for Agents & Staff administration, per-service commission
configurations, commission ledger, monthly payouts, and agent kiosk operations.
"""

import logging
from django.db.models import Q
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.mixins import SuccessResponseMixin
from apps.core.permissions import IsStaffOrAdmin, IsSystemAdmin
from apps.accounts.constants import (
    AccountStatus,
    CommissionServiceType,
    CommissionStatus,
    UserRole,
)
from apps.accounts.models import (
    AgentCommission,
    ServiceCommissionConfig,
    User,
)
from apps.accounts.services import AgentService
from apps.accounts.serializers import (
    AgentCommissionSerializer,
    AgentFacilitateServiceSerializer,
    AgentOnboardClientSerializer,
    AgentPayoutSerializer,
    ServiceCommissionConfigSerializer,
    StaffUserCreateSerializer,
    StaffUserListSerializer,
    StaffUserUpdateSerializer,
)

logger = logging.getLogger("apps.accounts.views.agent_views")

STAFF_ROLES = [
    UserRole.AGENT,
    UserRole.TUTOR,
    UserRole.TRAINING_ADMIN,
    UserRole.BOARD_REVIEWER,
    UserRole.ENTERPRISE_ADMIN,
    UserRole.SYSTEM_ADMIN,
]


class StaffOverviewMetricsView(SuccessResponseMixin, APIView):
    """
    GET /api/v1/auth/staff/metrics/
    Returns high-level statistics for the Agents & Staff control panel.
    """
    permission_classes = [IsSystemAdmin]

    def get(self, request, *args, **kwargs):
        metrics = AgentService.get_staff_overview_metrics()
        return self.success_response(data=metrics)


class StaffListCreateView(SuccessResponseMixin, generics.ListCreateAPIView):
    """
    GET /api/v1/auth/staff/
      List all staff members & agents with optional filtering by role and search.
    POST /api/v1/auth/staff/
      Create a new staff member or Sifo Drive field agent.
    """
    permission_classes = [IsSystemAdmin]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return StaffUserCreateSerializer
        return StaffUserListSerializer

    def get_queryset(self):
        queryset = (
            User.objects.filter(role__in=STAFF_ROLES)
            .select_related("agent_profile")
            .prefetch_related("clients_onboarded", "assigned_cohorts")
            .order_by("-created_at")
        )
        role = self.request.query_params.get("role")
        if role and role.upper() != "ALL":
            queryset = queryset.filter(role=role.upper())

        search = self.request.query_params.get("search")
        if search:
            search = search.strip()
            queryset = queryset.filter(
                Q(phone_number__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(email__icontains=search)
                | Q(agent_profile__agent_code__icontains=search)
                | Q(agent_profile__business_name__icontains=search)
            )
        return queryset

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        output = StaffUserListSerializer(user).data
        return self.success_response(
            data=output,
            message=f"Successfully created {user.role} user {user.phone_number}.",
            status_code=status.HTTP_201_CREATED,
        )


class StaffDetailView(SuccessResponseMixin, generics.RetrieveUpdateDestroyAPIView):
    """
    GET /api/v1/auth/staff/<id>/
      Retrieve details of a staff member / agent.
    PATCH /api/v1/auth/staff/<id>/
      Update staff information, status, or role.
    DELETE /api/v1/auth/staff/<id>/
      Deactivate staff member account.
    """
    permission_classes = [IsSystemAdmin]
    lookup_field = "id"
    lookup_url_kwarg = "staff_id"

    def get_queryset(self):
        return (
            User.objects.filter(role__in=STAFF_ROLES)
            .select_related("agent_profile")
            .prefetch_related("clients_onboarded", "assigned_cohorts")
        )

    def get_serializer_class(self):
        if self.request.method in ["PATCH", "PUT"]:
            return StaffUserUpdateSerializer
        return StaffUserListSerializer

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.status = AccountStatus.DEACTIVATED
        instance.save(update_fields=["is_active", "status", "updated_at"])


class ServiceCommissionConfigView(SuccessResponseMixin, APIView):
    """
    GET /api/v1/auth/agent-commissions/rates/
      List all per-service commission rates.
    PATCH /api/v1/auth/agent-commissions/rates/
      Update the commission fee in RWF for a given service type.
    """
    permission_classes = [IsSystemAdmin]

    def get(self, request, *args, **kwargs):
        AgentService.ensure_default_commission_configs()
        configs = ServiceCommissionConfig.objects.all().order_by("service_name")
        serializer = ServiceCommissionConfigSerializer(configs, many=True)
        return self.success_response(data=serializer.data)

    def patch(self, request, *args, **kwargs):
        service_type = request.data.get("service_type")
        commission_fee = request.data.get("commission_fee_rwf")
        client_price = request.data.get("default_client_price_rwf")
        notes = request.data.get("notes")

        if not service_type:
            return Response({"detail": "service_type is required."}, status=status.HTTP_400_BAD_REQUEST)

        AgentService.ensure_default_commission_configs()
        config = ServiceCommissionConfig.objects.filter(service_type=service_type).first()
        if not config:
            return Response({"detail": f"Service type {service_type} not found."}, status=status.HTTP_404_NOT_FOUND)

        if commission_fee is not None:
            config.commission_fee_rwf = int(commission_fee)
        if client_price is not None:
            config.default_client_price_rwf = int(client_price)
        if notes is not None:
            config.notes = notes.strip()
        config.save()

        logger.info("Admin updated commission for %s to %d RWF", service_type, config.commission_fee_rwf)
        return self.success_response(
            data=ServiceCommissionConfigSerializer(config).data,
            message=f"Updated {config.service_name} commission rate to {config.commission_fee_rwf} RWF.",
        )


class AgentCommissionsListView(SuccessResponseMixin, generics.ListAPIView):
    """
    GET /api/v1/auth/agent-commissions/
      List commission ledger items with filtering by agent_id, service_type, status.
    """
    permission_classes = [IsStaffOrAdmin]
    serializer_class = AgentCommissionSerializer

    def get_queryset(self):
        queryset = (
            AgentCommission.objects.all()
            .select_related("agent", "agent__agent_profile", "client")
            .order_by("-created_at")
        )

        # Field agent can only view their own commissions
        if self.request.user.role == UserRole.AGENT:
            queryset = queryset.filter(agent=self.request.user)
        else:
            agent_id = self.request.query_params.get("agent_id")
            if agent_id:
                queryset = queryset.filter(agent_id=agent_id)

        service_type = self.request.query_params.get("service_type")
        if service_type and service_type.upper() != "ALL":
            queryset = queryset.filter(service_type=service_type.upper())

        comm_status = self.request.query_params.get("status")
        if comm_status and comm_status.upper() != "ALL":
            queryset = queryset.filter(status=comm_status.upper())

        return queryset


class AgentMonthlyPayoutView(SuccessResponseMixin, APIView):
    """
    POST /api/v1/auth/agent-commissions/payout/
      Admin settles monthly (30-day) accrued commission payout for an agent.
    """
    permission_classes = [IsSystemAdmin]

    def post(self, request, *args, **kwargs):
        serializer = AgentPayoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        agent_id = serializer.validated_data["agent_id"]
        payout_amount = serializer.validated_data.get("payout_amount")
        notes = serializer.validated_data.get("notes", "")

        try:
            agent = User.objects.get(id=agent_id, role=UserRole.AGENT)
        except User.DoesNotExist:
            return Response({"detail": "Agent not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            settled_amount, records_count = AgentService.settle_monthly_payout(
                agent=agent,
                admin_user=request.user,
                payout_amount=payout_amount,
                notes=notes,
            )
        except ValueError as err:
            return Response({"detail": str(err)}, status=status.HTTP_400_BAD_REQUEST)

        profile = agent.agent_profile
        return self.success_response(
            data={
                "agent_id": str(agent.id),
                "agent_code": profile.agent_code,
                "amount_settled_rwf": settled_amount,
                "records_settled_count": records_count,
                "remaining_pending_balance_rwf": profile.pending_balance_rwf,
                "last_payout_date": str(profile.last_payout_date),
            },
            message=f"Successfully settled {settled_amount} RWF monthly payout for Agent {profile.agent_code}.",
        )


class AgentOnboardClientView(SuccessResponseMixin, APIView):
    """
    POST /api/v1/auth/agent/onboard-client/
      Allows an agent to create/register a client account on their behalf.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        if request.user.role != UserRole.AGENT and request.user.role != UserRole.SYSTEM_ADMIN:
            return Response({"detail": "Only agents or administrators can onboard clients."}, status=status.HTTP_403_FORBIDDEN)

        serializer = AgentOnboardClientSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        client = AgentService.onboard_client_by_agent(
            agent=request.user,
            phone_number=serializer.validated_data["phone_number"],
            first_name=serializer.validated_data["first_name"],
            last_name=serializer.validated_data["last_name"],
            role=serializer.validated_data.get("role", UserRole.GUEST),
            email=serializer.validated_data.get("email"),
        )
        return self.success_response(
            data={
                "id": str(client.id),
                "phone_number": client.phone_number,
                "full_name": client.full_name,
                "role": client.role,
                "created_by_agent": str(request.user.id),
            },
            message=f"Client {client.phone_number} successfully registered.",
            status_code=status.HTTP_201_CREATED,
        )


class AgentFacilitateServiceView(SuccessResponseMixin, APIView):
    """
    POST /api/v1/auth/agent/facilitate-service/
      Records a service facilitated by an agent for a client.
      Calculates and accrues the commission into the agent's ledger automatically.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        if request.user.role != UserRole.AGENT and request.user.role != UserRole.SYSTEM_ADMIN:
            return Response({"detail": "Only agents or administrators can record agent-facilitated services."}, status=status.HTTP_403_FORBIDDEN)

        serializer = AgentFacilitateServiceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        client_phone = serializer.validated_data["client_phone"].strip()
        client = User.objects.filter(phone_number=client_phone).first()

        service_type = serializer.validated_data["service_type"]
        service_ref = serializer.validated_data.get("service_reference", "")
        client_paid = serializer.validated_data.get("amount_paid_by_client_rwf")
        notes = serializer.validated_data.get("notes", "")

        commission = AgentService.record_service_commission(
            agent=request.user,
            client=client,
            service_type=service_type,
            service_reference=service_ref,
            amount_paid_by_client=client_paid,
            notes=notes,
        )

        return self.success_response(
            data=AgentCommissionSerializer(commission).data,
            message=f"Service recorded. Earned {commission.commission_amount_rwf} RWF commission.",
            status_code=status.HTTP_201_CREATED,
        )
