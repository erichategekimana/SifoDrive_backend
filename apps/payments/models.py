"""
apps/payments/models.py
========================
MoMo payment transaction models with idempotency guarantees.
"""
from django.db import models
from django.utils.translation import gettext_lazy as _
from apps.core.models import BaseModel


class Transaction(BaseModel):
    """An individual Mobile Money payment transaction."""
    PROVIDERS = [('MTN', 'MTN Mobile Money'), ('AIRTEL', 'Airtel Money')]
    FEE_TYPES = [
        ('STUDENT_TUITION', 'Student Tuition Fee'),
        ('GUEST_EXAM_PASS', 'Guest Exam Single Pass'),
        ('ENTERPRISE_LICENSE', 'Enterprise Lab License'),
        ('IREMBO_CONCIERGE', 'Irembo Concierge Fee'),
    ]
    STATUSES = [
        ('INITIATED', 'Initiated'),
        ('PENDING', 'Pending MoMo Approval'),
        ('SUCCESSFUL', 'Successful'),
        ('FAILED', 'Failed'),
        ('REFUNDED', 'Refunded'),
    ]
    payer = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='transactions')
    provider = models.CharField(_('Provider'), max_length=10, choices=PROVIDERS)
    fee_type = models.CharField(_('Fee Type'), max_length=25, choices=FEE_TYPES)
    amount = models.DecimalField(_('Amount (RWF)'), max_digits=12, decimal_places=2)
    currency = models.CharField(_('Currency'), max_length=5, default='RWF')
    phone_number = models.CharField(_('Payer Phone'), max_length=20)
    status = models.CharField(_('Status'), max_length=15, choices=STATUSES, default='INITIATED', db_index=True)
    provider_transaction_id = models.CharField(_('Provider TX ID'), max_length=200, blank=True, unique=True, null=True)
    idempotency_key = models.UUIDField(_('Idempotency Key'), unique=True)
    webhook_payload = models.JSONField(_('Webhook Payload'), null=True, blank=True)
    failed_reason = models.CharField(_('Failure Reason'), max_length=500, blank=True)
    completed_at = models.DateTimeField(_('Completed At'), null=True, blank=True)

    class Meta(BaseModel.Meta):
        verbose_name = _('Transaction')
        ordering = ['-created_at']

    def __str__(self):
        return f'[{self.provider}] {self.fee_type} — {self.amount} RWF [{self.status}]'

    @property
    def is_successful(self) -> bool:
        return self.status == 'SUCCESSFUL'
