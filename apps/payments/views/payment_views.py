"""
apps/payments/views/payment_views.py
====================================
Mobile Money Payments API views.
"""
from rest_framework import generics
from apps.core.mixins import SuccessResponseMixin
from apps.payments.models import Transaction
from apps.payments.serializers import TransactionSerializer


class TransactionListView(SuccessResponseMixin, generics.ListAPIView):
    """List authenticated user's transactions."""
    serializer_class = TransactionSerializer

    def get_queryset(self):
        return Transaction.objects.filter(payer=self.request.user)
