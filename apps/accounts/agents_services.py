"""
apps/accounts/agents_services.py
================================
Domain business services for Sifo Drive Agents and Staff management,
including per-service commission calculation, ledger accumulation,
client onboarding, and 30-day monthly payout cycles.
"""

from datetime import date, timedelta
import logging
import uuid
from typing import Any, Dict, List, Optional, Tuple

from django.db import transaction
from django.db.models import Count, Sum, Q
from django.utils import timezone

from apps.accounts.constants import (
    AccountStatus,
    CommissionServiceType,
    CommissionStatus,
    UserRole,
)
from apps.accounts.models import (
    AgentCommission,
    AgentProfile,
    ServiceCommissionConfig,
    User,
)

logger = logging.getLogger("apps.accounts.agents_services")


# Default commission configurations
DEFAULT_COMMISSIONS = [
    {
        "service_type": CommissionServiceType.BOOKING,
        "service_name": "BOOKING",
        "default_client_price_rwf": 2500,
        "commission_fee_rwf": 500,
        "notes": "Driving test booking reservation on Irembo.",
    },
    {
        "service_type": CommissionServiceType.SUBSCRIPTION,
        "service_name": "SUBSCRIPTION",
        "default_client_price_rwf": 15000,
        "commission_fee_rwf": 1000,
        "notes": "Course and curriculum access subscription.",
    },
    {
        "service_type": CommissionServiceType.EXAM_PURCHASE,
        "service_name": "EXAM_PURCHASE",
        "default_client_price_rwf": 2000,
        "commission_fee_rwf": 300,
        "notes": "Mock exam test bundle package purchase.",
    },
    {
        "service_type": CommissionServiceType.LEARNING_FEE,
        "service_name": "LEARNING_FEE",
        "default_client_price_rwf": 25000,
        "commission_fee_rwf": 1500,
        "notes": "Learning and tuition fee payment.",
    },
    {
        "service_type": CommissionServiceType.OTHER,
        "service_name": "OTHER",
        "default_client_price_rwf": 5000,
        "commission_fee_rwf": 500,
        "notes": "Other kiosk client service.",
    },
]


class AgentService:
    """Business service managing Sifo Drive field agents, commissions, and staff operations."""

    @classmethod
    def ensure_default_commission_configs(cls) -> None:
        """Seed or verify default per-service commission rates if missing."""
        for item in DEFAULT_COMMISSIONS:
            ServiceCommissionConfig.objects.get_or_create(
                service_type=item["service_type"],
                defaults={
                    "service_name": item["service_name"],
                    "default_client_price_rwf": item["default_client_price_rwf"],
                    "commission_fee_rwf": item["commission_fee_rwf"],
                    "notes": item["notes"],
                    "is_active": True,
                },
            )

    @classmethod
    def generate_agent_code(cls) -> str:
        """Generate a clean, unique agent code (e.g. SIFO-AGT-010)."""
        count = AgentProfile.objects.count() + 1
        code = f"SIFO-AGT-{count:03d}"
        while AgentProfile.objects.filter(agent_code=code).exists():
            count += 1
            code = f"SIFO-AGT-{count:03d}"
        return code

    @classmethod
    @transaction.atomic
    def create_agent(
        cls,
        phone_number: str,
        first_name: str,
        last_name: str,
        email: Optional[str] = None,
        password: Optional[str] = None,
        business_name: str = "",
        national_id: str = "",
        district: str = "",
        sector: str = "",
    ) -> User:
        """Create a new User with role=AGENT and an associated AgentProfile."""
        user = User.objects.create(
            phone_number=phone_number.strip(),
            first_name=first_name.strip(),
            last_name=last_name.strip(),
            email=email.strip().lower() if email else None,
            role=UserRole.AGENT,
            status=AccountStatus.ACTIVE,
            is_active=True,
            terms_of_service_accepted=True,
            terms_of_service_accepted_at=timezone.now(),
        )
        if password:
            user.set_password(password)
            user.save(update_fields=["password"])

        agent_code = cls.generate_agent_code()
        AgentProfile.objects.create(
            user=user,
            agent_code=agent_code,
            business_name=business_name.strip(),
            national_id_number=national_id.strip(),
            district=district.strip(),
            sector=sector.strip(),
            is_approved=True,
        )
        logger.info("Created Sifo Drive Agent %s (%s)", agent_code, user.phone_number)
        return user

    @classmethod
    @transaction.atomic
    def onboard_client_by_agent(
        cls,
        agent: User,
        phone_number: str,
        first_name: str,
        last_name: str,
        role: str = UserRole.GUEST,
        email: Optional[str] = None,
        national_id: Optional[str] = None,
    ) -> User:
        """Register a new student or guest client account facilitated by an agent."""
        if agent.role != UserRole.AGENT and agent.role != UserRole.SYSTEM_ADMIN:
            raise ValueError("Only verified Sifo Drive agents or administrators can onboard clients.")

        client, created = User.objects.get_or_create(
            phone_number=phone_number.strip(),
            defaults={
                "first_name": first_name.strip(),
                "last_name": last_name.strip(),
                "email": email.strip().lower() if email else None,
                "role": role,
                "status": AccountStatus.ACTIVE,
                "is_active": True,
                "created_by_agent": agent if agent.role == UserRole.AGENT else None,
                "terms_of_service_accepted": True,
                "terms_of_service_accepted_at": timezone.now(),
            },
        )
        if not created and not client.created_by_agent and agent.role == UserRole.AGENT:
            client.created_by_agent = agent
            client.save(update_fields=["created_by_agent"])

        logger.info("Client %s onboarded by Agent %s", client.phone_number, agent.phone_number)
        return client

    @classmethod
    def get_commission_fee(cls, service_type: str) -> int:
        """Look up the configured commission fee in RWF for a given service."""
        cls.ensure_default_commission_configs()
        config = ServiceCommissionConfig.objects.filter(service_type=service_type, is_active=True).first()
        if config:
            return config.commission_fee_rwf
        return 500  # Fallback standard fee

    @classmethod
    @transaction.atomic
    def record_service_commission(
        cls,
        agent: User,
        client: Optional[User],
        service_type: str,
        service_reference: str = "",
        amount_paid_by_client: Optional[int] = None,
        custom_commission: Optional[int] = None,
        notes: str = "",
    ) -> AgentCommission:
        """
        Record an accrued commission for an agent who completed/facilitated a service for a client.
        Calculates commission from ServiceCommissionConfig and updates agent accrued balance.
        """
        if agent.role != UserRole.AGENT:
            raise ValueError(f"User {agent.phone_number} is not an AGENT.")

        cls.ensure_default_commission_configs()
        config = ServiceCommissionConfig.objects.filter(service_type=service_type, is_active=True).first()

        client_paid = amount_paid_by_client
        if client_paid is None:
            client_paid = config.default_client_price_rwf if config else 2500

        commission_amount = custom_commission
        if commission_amount is None:
            commission_amount = config.commission_fee_rwf if config else 500

        commission = AgentCommission.objects.create(
            agent=agent,
            client=client,
            service_type=service_type,
            service_reference=service_reference.strip(),
            amount_paid_by_client_rwf=client_paid,
            commission_amount_rwf=commission_amount,
            status=CommissionStatus.ACCRUED,
            notes=notes.strip(),
        )

        profile, _ = AgentProfile.objects.get_or_create(
            user=agent,
            defaults={"agent_code": cls.generate_agent_code()}
        )
        profile.total_accrued_rwf += commission_amount
        profile.save(update_fields=["total_accrued_rwf", "updated_at"])

        logger.info(
            "Accrued %d RWF commission for Agent %s on service %s (Ref: %s)",
            commission_amount,
            agent.phone_number,
            service_type,
            service_reference,
        )
        return commission

    @classmethod
    @transaction.atomic
    def settle_monthly_payout(
        cls,
        agent: User,
        admin_user: User,
        payout_amount: Optional[int] = None,
        notes: str = "",
    ) -> Tuple[int, int]:
        """
        Settle and mark accrued commissions as PAID_OUT for the 30-day payout cycle.
        Returns (amount_paid, commission_records_count).
        """
        if agent.role != UserRole.AGENT:
            raise ValueError("Target user is not an agent.")

        profile = getattr(agent, "agent_profile", None)
        if not profile:
            raise ValueError("Agent profile not found.")

        pending_balance = profile.pending_balance_rwf
        if pending_balance <= 0:
            raise ValueError(f"Agent {agent.phone_number} has no pending commission balance to settle.")

        to_settle = payout_amount if payout_amount is not None else pending_balance
        if to_settle <= 0 or to_settle > pending_balance:
            raise ValueError(f"Invalid payout amount: {to_settle}. Available balance: {pending_balance} RWF.")

        batch_id = f"PAY-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        accrued_items = AgentCommission.objects.filter(
            agent=agent,
            status=CommissionStatus.ACCRUED
        ).order_by("created_at")

        settled_so_far = 0
        items_settled_count = 0
        for item in accrued_items:
            if settled_so_far + item.commission_amount_rwf <= to_settle:
                item.status = CommissionStatus.PAID_OUT
                item.paid_out_at = timezone.now()
                item.paid_out_by = admin_user
                item.payout_batch_id = batch_id
                item.save(update_fields=["status", "paid_out_at", "paid_out_by", "payout_batch_id", "updated_at"])
                settled_so_far += item.commission_amount_rwf
                items_settled_count += 1
            else:
                break

        actual_settled = settled_so_far if settled_so_far > 0 else to_settle
        profile.total_paid_out_rwf += actual_settled
        profile.last_payout_date = timezone.now().date()
        profile.save(update_fields=["total_paid_out_rwf", "last_payout_date", "updated_at"])

        logger.info(
            "Settled monthly payout of %d RWF for Agent %s (Batch %s, Records: %d)",
            actual_settled,
            agent.phone_number,
            batch_id,
            items_settled_count,
        )
        return actual_settled, items_settled_count

    @classmethod
    def get_agent_metrics(cls, agent: User) -> Dict[str, Any]:
        """Compute detailed performance, commissions, and 30-day payout timeline for an agent."""
        profile, _ = AgentProfile.objects.get_or_create(
            user=agent,
            defaults={"agent_code": cls.generate_agent_code()}
        )
        today = timezone.now().date()
        last_payout = profile.last_payout_date or profile.created_at.date()
        days_since_last_payout = (today - last_payout).days
        next_payout_due_date = last_payout + timedelta(days=30)
        days_until_next_payout = max(0, (next_payout_due_date - today).days)

        clients_count = agent.clients_onboarded.count()
        total_services_count = agent.commissions_earned.count()

        services_breakdown = (
            agent.commissions_earned.values("service_type")
            .annotate(
                count=Count("id"),
                total_commissions=Sum("commission_amount_rwf")
            )
        )

        return {
            "agent_code": profile.agent_code,
            "business_name": profile.business_name,
            "district": profile.district,
            "sector": profile.sector,
            "total_accrued_rwf": profile.total_accrued_rwf,
            "total_paid_out_rwf": profile.total_paid_out_rwf,
            "pending_balance_rwf": profile.pending_balance_rwf,
            "last_payout_date": profile.last_payout_date,
            "next_payout_due_date": next_payout_due_date,
            "days_since_last_payout": days_since_last_payout,
            "days_until_next_payout": days_until_next_payout,
            "is_payout_due": days_since_last_payout >= 30 and profile.pending_balance_rwf > 0,
            "clients_onboarded_count": clients_count,
            "total_services_count": total_services_count,
            "services_breakdown": list(services_breakdown),
        }

    @classmethod
    def get_staff_overview_metrics(cls) -> Dict[str, Any]:
        """Compute platform-wide metrics for the Agents & Staff console."""
        staff_qs = User.objects.filter(
            role__in=[
                UserRole.AGENT,
                UserRole.TUTOR,
                UserRole.TRAINING_ADMIN,
                UserRole.BOARD_REVIEWER,
                UserRole.ENTERPRISE_ADMIN,
                UserRole.SYSTEM_ADMIN,
            ]
        )
        total_staff = staff_qs.count()
        total_agents = staff_qs.filter(role=UserRole.AGENT).count()
        total_tutors = staff_qs.filter(role=UserRole.TUTOR).count()
        total_training_admins = staff_qs.filter(role=UserRole.TRAINING_ADMIN).count()
        total_board_reviewers = staff_qs.filter(role=UserRole.BOARD_REVIEWER).count()
        total_enterprise_admins = staff_qs.filter(role=UserRole.ENTERPRISE_ADMIN).count()

        commissions_agg = AgentCommission.objects.aggregate(
            total_accrued=Sum("commission_amount_rwf"),
            total_paid_out=Sum(
                "commission_amount_rwf",
                filter=Q(status=CommissionStatus.PAID_OUT)
            ),
            total_unpaid=Sum(
                "commission_amount_rwf",
                filter=Q(status=CommissionStatus.ACCRUED)
            ),
        )

        return {
            "total_staff": total_staff,
            "total_agents": total_agents,
            "total_tutors": total_tutors,
            "total_training_admins": total_training_admins,
            "total_board_reviewers": total_board_reviewers,
            "total_enterprise_admins": total_enterprise_admins,
            "total_commissions_generated_rwf": commissions_agg["total_accrued"] or 0,
            "total_commissions_paid_out_rwf": commissions_agg["total_paid_out"] or 0,
            "total_unpaid_commission_balance_rwf": commissions_agg["total_unpaid"] or 0,
        }
