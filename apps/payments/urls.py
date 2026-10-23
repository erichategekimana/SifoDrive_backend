"""apps/payments/urls.py
Mobile Money Payments URL routes."""
from django.urls import path
from apps.payments.views import MTNMomoWebhookView, TransactionListView

app_name = "payments"

urlpatterns = [
    # Production MTN MoMo Webhook Callback Endpoint
    path("momo/callback/", MTNMomoWebhookView.as_view(), name="momo_webhook"),

    # Authenticated User Transactions History
    path("transactions/", TransactionListView.as_view(), name="transactions_list"),
]
