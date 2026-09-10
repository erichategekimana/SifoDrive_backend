"""
apps/irembo/models.py
======================
Irembo physical test booking concierge — state machine model.
"""
from django.db import models
from django.utils.translation import gettext_lazy as _
from apps.core.models import BaseModel


class BookingOrder(BaseModel):
    """
    Represents an Irembo driving test booking request.
    Progresses through a strict state machine enforced at the service layer.
    """
    STATES = [
        ('SUBMITTED_UNPAID', 'Submitted — Awaiting Payment'),
        ('QUEUED_PAID', 'Queued — Payment Confirmed'),
        ('PROCESSING', 'Processing — Agent Assigned'),
        ('CONFIRMED', 'Confirmed — Slot Booked'),
        ('SLOTS_EXHAUSTED', 'Slots Exhausted'),
        ('REFUND_REQUESTED', 'Refund Requested'),
        ('REFUNDED', 'Refunded'),
    ]
    # Applicant details
    applicant = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='irembo_bookings')
    national_id_encrypted = models.TextField(_('National ID (Encrypted)'))
    full_legal_name = models.CharField(_('Full Legal Name'), max_length=200)
    date_of_birth = models.DateField(_('Date of Birth'))
    license_category = models.CharField(_('License Category'), max_length=5)
    preferred_district = models.CharField(_('Preferred District'), max_length=100)
    phone_number = models.CharField(_('Contact Phone'), max_length=20)
    # State machine
    state = models.CharField(_('State'), max_length=25, choices=STATES, default='SUBMITTED_UNPAID', db_index=True)
    ticket_number = models.CharField(_('Ticket Number'), max_length=20, unique=True, blank=True)
    # Agent processing
    assigned_agent = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_bookings')
    irembo_application_number = models.CharField(_('Irembo Application Number'), max_length=50, blank=True)
    irembo_confirmation_pdf = models.FileField(_('Confirmation PDF'), upload_to='irembo/confirmations/%Y/%m/', null=True, blank=True)
    confirmed_test_date = models.DateField(_('Test Date'), null=True, blank=True)
    confirmed_test_time = models.TimeField(_('Test Time'), null=True, blank=True)
    confirmed_venue = models.CharField(_('Venue'), max_length=200, blank=True)
    agent_notes = models.TextField(_('Agent Notes'), blank=True)
    queued_at = models.DateTimeField(_('Queued At'), null=True, blank=True)

    class Meta(BaseModel.Meta):
        verbose_name = _('Booking Order')
        ordering = ['queued_at', 'created_at']

    def __str__(self):
        return f'Booking {self.ticket_number} — {self.full_legal_name} [{self.state}]'
