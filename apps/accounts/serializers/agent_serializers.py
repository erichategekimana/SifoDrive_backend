from typing import Optional
from rest_framework import serializers

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


class ServiceCommissionConfigSerializer(serializers.ModelSerializer):
    """Serializer for per-service commission configurations (editable by admin)."""

    class Meta:
        model = ServiceCommissionConfig
        fields = [
            "id",
            "service_type",
            "service_name",
            "default_client_price_rwf",
            "commission_fee_rwf",
            "is_active",
            "notes",
            "updated_at",
        ]
        read_only_fields = ["id", "service_type", "updated_at"]


class AgentCommissionSerializer(serializers.ModelSerializer):
    """Detailed ledger record of an accrued or settled commission."""
    agent_name = serializers.CharField(source="agent.full_name", read_only=True)
    agent_phone = serializers.CharField(source="agent.phone_number", read_only=True)
    agent_code = serializers.SerializerMethodField()
    client_name = serializers.CharField(source="client.full_name", read_only=True, default="")
    client_phone = serializers.CharField(source="client.phone_number", read_only=True, default="")

    def get_agent_code(self, obj) -> str:
        profile = getattr(obj.agent, "agent_profile", None)
        return profile.agent_code if profile else ""

    class Meta:
        model = AgentCommission
        fields = [
            "id",
            "agent",
            "agent_name",
            "agent_phone",
            "agent_code",
            "client",
            "client_name",
            "client_phone",
            "service_type",
            "service_reference",
            "amount_paid_by_client_rwf",
            "commission_amount_rwf",
            "status",
            "paid_out_at",
            "payout_batch_id",
            "notes",
            "created_at",
        ]
        read_only_fields = fields


class StaffUserListSerializer(serializers.ModelSerializer):
    """Unified serializer for all staff members and field agents."""
    agent_code = serializers.SerializerMethodField()
    business_name = serializers.SerializerMethodField()
    district = serializers.SerializerMethodField()
    sector = serializers.SerializerMethodField()
    total_accrued_rwf = serializers.SerializerMethodField()
    total_paid_out_rwf = serializers.SerializerMethodField()
    pending_balance_rwf = serializers.SerializerMethodField()
    last_payout_date = serializers.SerializerMethodField()
    next_payout_due_date = serializers.SerializerMethodField()
    clients_onboarded_count = serializers.SerializerMethodField()
    assigned_cohorts_count = serializers.SerializerMethodField()

    def get_agent_code(self, obj) -> str:
        profile = getattr(obj, "agent_profile", None)
        return profile.agent_code if profile else ""

    def get_business_name(self, obj) -> str:
        profile = getattr(obj, "agent_profile", None)
        return profile.business_name if profile else ""

    def get_district(self, obj) -> str:
        profile = getattr(obj, "agent_profile", None)
        return profile.district if profile else ""

    def get_sector(self, obj) -> str:
        profile = getattr(obj, "agent_profile", None)
        return profile.sector if profile else ""

    def get_total_accrued_rwf(self, obj) -> int:
        profile = getattr(obj, "agent_profile", None)
        return profile.total_accrued_rwf if profile else 0

    def get_total_paid_out_rwf(self, obj) -> int:
        profile = getattr(obj, "agent_profile", None)
        return profile.total_paid_out_rwf if profile else 0

    def get_pending_balance_rwf(self, obj) -> int:
        profile = getattr(obj, "agent_profile", None)
        return profile.pending_balance_rwf if profile else 0

    def get_last_payout_date(self, obj) -> Optional[str]:
        profile = getattr(obj, "agent_profile", None)
        return str(profile.last_payout_date) if profile and profile.last_payout_date else None

    def get_next_payout_due_date(self, obj) -> Optional[str]:
        if obj.role != UserRole.AGENT:
            return None
        from apps.accounts.services import AgentService
        metrics = AgentService.get_agent_metrics(obj)
        return str(metrics.get("next_payout_due_date")) if metrics else None

    def get_clients_onboarded_count(self, obj) -> int:
        if obj.role == UserRole.AGENT:
            return obj.clients_onboarded.count()
        return 0

    def get_assigned_cohorts_count(self, obj) -> int:
        if obj.role == UserRole.TUTOR:
            return getattr(obj, "assigned_cohorts", None).count() if hasattr(obj, "assigned_cohorts") else 0
        return 0

    class Meta:
        model = User
        fields = [
            "id",
            "phone_number",
            "first_name",
            "last_name",
            "full_name",
            "email",
            "role",
            "status",
            "is_active",
            "school_name",
            "agent_code",
            "business_name",
            "district",
            "sector",
            "total_accrued_rwf",
            "total_paid_out_rwf",
            "pending_balance_rwf",
            "last_payout_date",
            "next_payout_due_date",
            "clients_onboarded_count",
            "assigned_cohorts_count",
            "last_login",
            "last_login_ip",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class StaffUserCreateSerializer(serializers.Serializer):
    """Create a new staff member or Sifo Drive field agent."""
    phone_number = serializers.CharField(max_length=20)
    first_name = serializers.CharField(max_length=100)
    last_name = serializers.CharField(max_length=100)
    email = serializers.EmailField(required=False, allow_null=True, allow_blank=True)
    role = serializers.ChoiceField(
        choices=[
            UserRole.AGENT,
            UserRole.TUTOR,
            UserRole.TRAINING_ADMIN,
            UserRole.BOARD_REVIEWER,
            UserRole.ENTERPRISE_ADMIN,
            UserRole.SYSTEM_ADMIN,
        ]
    )
    password = serializers.CharField(max_length=128, required=False, allow_blank=True)
    # Agent specific fields
    business_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    national_id_number = serializers.CharField(max_length=30, required=False, allow_blank=True)
    district = serializers.CharField(max_length=50, required=False, allow_blank=True)
    sector = serializers.CharField(max_length=50, required=False, allow_blank=True)
    # Enterprise specific fields
    school_name = serializers.CharField(max_length=200, required=False, allow_blank=True)

    def validate_phone_number(self, value):
        val = value.strip()
        if User.objects.filter(phone_number=val).exists():
            raise serializers.ValidationError("A user with this phone number already exists.")
        return val

    def create(self, validated_data):
        role = validated_data["role"]
        from apps.accounts.services import AgentService

        if role == UserRole.AGENT:
            return AgentService.create_agent(
                phone_number=validated_data["phone_number"],
                first_name=validated_data["first_name"],
                last_name=validated_data["last_name"],
                email=validated_data.get("email"),
                password=validated_data.get("password") or "Agent@123456",
                business_name=validated_data.get("business_name", ""),
                national_id=validated_data.get("national_id_number", ""),
                district=validated_data.get("district", ""),
                sector=validated_data.get("sector", ""),
            )

        user = User.objects.create(
            phone_number=validated_data["phone_number"].strip(),
            first_name=validated_data["first_name"].strip(),
            last_name=validated_data["last_name"].strip(),
            email=validated_data.get("email"),
            role=role,
            status=AccountStatus.ACTIVE,
            is_active=True,
            school_name=validated_data.get("school_name", "").strip(),
            terms_of_service_accepted=True,
        )
        pwd = validated_data.get("password") or "Staff@123456"
        user.set_password(pwd)
        user.save(update_fields=["password"])
        return user


class StaffUserUpdateSerializer(serializers.ModelSerializer):
    """Update an existing staff member or agent's status or role."""
    business_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    district = serializers.CharField(max_length=50, required=False, allow_blank=True)
    sector = serializers.CharField(max_length=50, required=False, allow_blank=True)

    class Meta:
        model = User
        fields = [
            "first_name",
            "last_name",
            "email",
            "role",
            "status",
            "is_active",
            "school_name",
            "business_name",
            "district",
            "sector",
        ]

    def update(self, instance, validated_data):
        b_name = validated_data.pop("business_name", None)
        dist = validated_data.pop("district", None)
        sec = validated_data.pop("sector", None)

        for attr, val in validated_data.items():
            setattr(instance, attr, val)
        instance.save()

        if instance.role == UserRole.AGENT and (b_name is not None or dist is not None or sec is not None):
            from apps.accounts.services import AgentService
            profile, _ = AgentProfile.objects.get_or_create(
                user=instance,
                defaults={"agent_code": AgentService.generate_agent_code()}
            )
            if b_name is not None:
                profile.business_name = b_name
            if dist is not None:
                profile.district = dist
            if sec is not None:
                profile.sector = sec
            profile.save()

        return instance


class AgentPayoutSerializer(serializers.Serializer):
    """Admin settlement of an agent's monthly accumulated commission."""
    agent_id = serializers.UUIDField()
    payout_amount = serializers.IntegerField(required=False, min_value=1)
    notes = serializers.CharField(required=False, allow_blank=True)


class AgentOnboardClientSerializer(serializers.Serializer):
    """Agent action: Onboard and create a new client account."""
    phone_number = serializers.CharField(max_length=20)
    first_name = serializers.CharField(max_length=100)
    last_name = serializers.CharField(max_length=100)
    email = serializers.EmailField(required=False, allow_null=True, allow_blank=True)
    role = serializers.ChoiceField(choices=[UserRole.GUEST, UserRole.STUDENT], default=UserRole.GUEST)


class AgentFacilitateServiceSerializer(serializers.Serializer):
    """Agent action: Record a completed service facilitated for a client."""
    client_phone = serializers.CharField(max_length=20)
    service_type = serializers.ChoiceField(choices=CommissionServiceType.choices)
    service_reference = serializers.CharField(max_length=100, required=False, allow_blank=True)
    amount_paid_by_client_rwf = serializers.IntegerField(required=False, min_value=0)
    notes = serializers.CharField(required=False, allow_blank=True)
