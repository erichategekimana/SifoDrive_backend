"""
apps/payments/views/webhook_views.py
====================================
Production webhook callback endpoints for Mobile Money providers (MTN & Airtel).
Receives asynchronous payment notifications when transactions are completed or failed.
"""
import logging
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from django.conf import settings

from apps.payments.services.payment_service import PaymentService

logger = logging.getLogger(__name__)


class MTNMomoWebhookView(APIView):
    """
    Receives incoming asynchronous payment notifications from MTN MoMo Collection API.
    Supports both POST and PUT methods as per MTN MoMo specification.
    """
    permission_classes = [AllowAny]
    authentication_classes = []  # Public endpoint called by MTN gateway

    def _process_callback(self, request):
        payload = request.data or {}
        headers = request.headers or {}
        query_params = request.query_params or {}

        logger.info(
            "Received MTN MoMo callback: Headers=%s, Query=%s, Body=%s",
            dict(headers), dict(query_params), payload
        )

        # Optional security token validation if configured in .env
        configured_secret = getattr(settings, "MTN_MOMO", {}).get("WEBHOOK_SECRET", "")
        if configured_secret:
            incoming_token = (
                headers.get("X-Callback-Token")
                or query_params.get("token")
                or payload.get("token")
            )
            if incoming_token != configured_secret:
                logger.warning("MTN MoMo webhook rejected: Invalid or missing webhook token.")
                return Response(
                    {"error": "Unauthorized webhook token."},
                    status=status.HTTP_401_UNAUTHORIZED,
                )

        # Process callback and fulfill credits / update PostgreSQL Transaction
        result = PaymentService.handle_momo_webhook(
            payload=payload,
            headers=headers,
            query_params=query_params,
        )

        return Response(
            {
                "status": "RECEIVED",
                "processed": result.get("success", False),
                "reference_id": result.get("reference_id"),
                "payment_status": result.get("payment_status"),
                "message": result.get("message", "Callback processed successfully."),
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request, *args, **kwargs):
        return self._process_callback(request)

    def put(self, request, *args, **kwargs):
        return self._process_callback(request)
