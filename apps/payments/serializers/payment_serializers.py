"""
apps/payments/serializers/payment_serializers.py
================================================
Serializers for MoMo payment transactions.
"""
from rest_framework import serializers
from apps.payments.models import Transaction


class TransactionSerializer(serializers.ModelSerializer):
    """Read/Write serializer for transactions."""
    class Meta:
        model = Transaction
        fields = [
            'id',
            'payer',
            'provider',
            'fee_type',
            'amount',
            'currency',
            'phone_number',
            'status',
            'provider_transaction_id',
            'completed_at',
            'created_at',
        ]
        read_only_fields = ['id', 'status', 'provider_transaction_id', 'completed_at', 'created_at']
