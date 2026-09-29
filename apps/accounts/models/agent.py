from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel, UUIDModel
from apps.accounts.constants import (
    CommissionServiceType,
    CommissionStatus,
    UserRole,
)
from apps.accounts.models.user import User


class AgentProfile(UUIDModel, TimeStampedModel):
    """
    Profile data for Sifo Drive field/kiosk agents.
    Tracks agent identification, commission accumulation, and 30-day payout cycles.
    """

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="agent_profile",
        limit_choices_to={"role": UserRole.AGENT},
    )
    agent_code = models.CharField(
        _("Agent Code"),
        max_length=30,
        unique=True,
        db_index=True,
        help_text=_("Unique identifier (e.g. SIFO-AGT-001)."),
    )
    business_name = models.CharField(
        _("Kiosk / Agency Business Name"),
        max_length=150,
        blank=True,
        default="",
        help_text=_("Name of the agent's kiosk, cyber café, or agency location."),
    )
    national_id_number = models.CharField(
        _("National ID Number"),
        max_length=30,
        blank=True,
        default="",
    )
    district = models.CharField(_("District"), max_length=50, blank=True, default="")
    sector = models.CharField(_("Sector"), max_length=50, blank=True, default="")
    total_accrued_rwf = models.PositiveIntegerField(
        _("Total Accrued Commissions (RWF)"),
        default=0,
        help_text=_("All-time commission calculated from client services."),
    )
    total_paid_out_rwf = models.PositiveIntegerField(
        _("Total Paid Out (RWF)"),
        default=0,
        help_text=_("All-time commission settled and paid to agent by admin."),
    )
    last_payout_date = models.DateField(
        _("Last Payout Date"),
        null=True,
        blank=True,
        help_text=_("Date of the most recent monthly settlement."),
    )
    is_approved = models.BooleanField(_("Is Approved"), default=True)

    class Meta:
        app_label = 'accounts'
        verbose_name = _("Agent Profile")
        verbose_name_plural = _("Agent Profiles")
        ordering = ["agent_code"]

    def __str__(self) -> str:
        return f"Agent {self.agent_code} — {self.user.full_name or self.user.phone_number}"

    @property
    def pending_balance_rwf(self) -> int:
        """Calculated commission balance awaiting monthly payout."""
        return max(0, self.total_accrued_rwf - self.total_paid_out_rwf)


class ServiceCommissionConfig(UUIDModel, TimeStampedModel):
    """
    Configurable commission fees per service type.
    System admin can update the commission fee in RWF for any service at any time.
    """

    service_type = models.CharField(
        _("Service Type"),
        max_length=30,
        choices=CommissionServiceType.choices,
        unique=True,
        db_index=True,
    )
    service_name = models.CharField(_("Service Display Name"), max_length=120)
    default_client_price_rwf = models.PositiveIntegerField(
        _("Default Client Price (RWF)"),
        default=2500,
        help_text=_("Standard price charged to clients for this service."),
    )
    commission_fee_rwf = models.PositiveIntegerField(
        _("Agent Commission Fee (RWF)"),
        default=500,
        help_text=_("Flat commission earned by agent per completed service."),
    )
    is_active = models.BooleanField(_("Is Active"), default=True)
    notes = models.TextField(_("Internal Notes"), blank=True, default="")

    class Meta:
        app_label = 'accounts'
        verbose_name = _("Service Commission Config")
        verbose_name_plural = _("Service Commission Configs")
        ordering = ["service_name"]

    def __str__(self) -> str:
        return f"{self.service_name}: {self.commission_fee_rwf} RWF commission"


class AgentCommission(UUIDModel, TimeStampedModel):
    """
    Commission ledger entry recorded whenever an agent facilitates a client service.
    Money does not go directly to agent immediately; it accumulates as calculated
    earnings settled monthly (every 30 days) by system administrator.
    """

    agent = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="commissions_earned",
        limit_choices_to={"role": UserRole.AGENT},
        verbose_name=_("Agent"),
    )
    client = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="agent_facilitated_services",
        verbose_name=_("Client"),
    )
    service_type = models.CharField(
        _("Service Type"),
        max_length=30,
        choices=CommissionServiceType.choices,
        default=CommissionServiceType.BOOKING,
        db_index=True,
    )
    service_reference = models.CharField(
        _("Service Reference"),
        max_length=100,
        blank=True,
        default="",
        help_text=_("Booking ticket number, payment transaction UUID, or subscription reference."),
    )
    amount_paid_by_client_rwf = models.PositiveIntegerField(
        _("Amount Paid by Client (RWF)"),
        default=2500,
    )
    commission_amount_rwf = models.PositiveIntegerField(
        _("Commission Fee Earned (RWF)"),
        default=500,
    )
    status = models.CharField(
        _("Commission Status"),
        max_length=20,
        choices=CommissionStatus.choices,
        default=CommissionStatus.ACCRUED,
        db_index=True,
    )
    paid_out_at = models.DateTimeField(_("Paid Out At"), null=True, blank=True)
    paid_out_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payouts_administered",
        verbose_name=_("Settled By Admin"),
    )
    payout_batch_id = models.CharField(_("Payout Batch ID"), max_length=50, blank=True, default="")
    notes = models.TextField(_("Internal Remarks"), blank=True, default="")

    class Meta:
        app_label = 'accounts'
        verbose_name = _("Agent Commission Record")
        verbose_name_plural = _("Agent Commission Records")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"[{self.status}] {self.agent.phone_number} — {self.service_type}: {self.commission_amount_rwf} RWF"
