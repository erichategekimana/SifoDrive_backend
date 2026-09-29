from django.db.models import Q
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView

from apps.core.mixins import SuccessResponseMixin
from apps.core.pagination import StandardResultsPagination
from apps.core.permissions import IsAdminLevel, IsSystemAdmin
from apps.examinations.models import Certificate, CertificateTemplate
from apps.examinations.serializers import (
    CertificateSerializer,
    CertificateTemplateSerializer,
)
from apps.examinations.services import CertificateService


class AdminCertificateListView(SuccessResponseMixin, generics.ListAPIView):
    """List issued certificates with search and filter."""
    permission_classes = [IsAuthenticated, IsAdminLevel]
    serializer_class = CertificateSerializer
    pagination_class = StandardResultsPagination

    def get_queryset(self):
        qs = Certificate.objects.all().order_by("-created_at")
        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(
                Q(certificate_number__icontains=search)
                | Q(student_name__icontains=search)
                | Q(student_code__icontains=search)
            )
        track = self.request.query_params.get("track_type")
        if track:
            qs = qs.filter(track_type=track.upper())
        return qs


class AdminCertificateDetailView(SuccessResponseMixin, generics.RetrieveAPIView):
    """View details of an individual issued certificate."""
    permission_classes = [IsAuthenticated, IsAdminLevel]
    serializer_class = CertificateSerializer
    queryset = Certificate.objects.all()


class AdminCertificateTemplateListView(SuccessResponseMixin, APIView):
    """
    Lists all 3 certificate templates (Student, Guest, Enterprise).
    Ensures default templates exist before returning.
    """
    permission_classes = [IsAuthenticated, IsAdminLevel]

    def get(self, request, *args, **kwargs):
        CertificateService.ensure_default_templates()
        templates = CertificateTemplate.objects.all().order_by("template_type")
        serializer = CertificateTemplateSerializer(templates, many=True)
        return self.success_response(data=serializer.data, message="Certificate templates retrieved.")


class AdminCertificateTemplateDetailView(SuccessResponseMixin, generics.RetrieveUpdateAPIView):
    """
    Retrieve or update a specific certificate template (Student, Guest, Enterprise).
    Allows updating declaration wording, confirmation notes, logo URL, and digital signatures.
    Read is allowed for Admin Level (including Training Admin), but modification is restricted to System Admin.
    """
    serializer_class = CertificateTemplateSerializer
    queryset = CertificateTemplate.objects.all()

    def get_permissions(self):
        if self.request.method in ("PUT", "PATCH"):
            return [IsAuthenticated(), IsSystemAdmin()]
        return [IsAuthenticated(), IsAdminLevel()]


class PublicCertificateVerifyView(SuccessResponseMixin, APIView):
    """
    Public verification endpoint accessed via QR code scan or verification URL:
    GET /api/v1/examinations/verify/<verification_hash>/
    Allows anyone to verify legitimacy without authentication.
    """
    permission_classes = [AllowAny]

    def get(self, request, hash_or_code, *args, **kwargs):
        cert = Certificate.objects.filter(
            Q(verification_hash=hash_or_code) | Q(certificate_number__iexact=hash_or_code)
        ).first()

        if not cert or not cert.is_valid:
            return self.error_response(
                code="INVALID_CERTIFICATE",
                message="Certificate not found or has been revoked.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        return self.success_response(
            data={
                "is_valid": cert.is_valid,
                "certificate_number": cert.certificate_number,
                "student_name": cert.student_name,
                "student_code": cert.student_code,
                "track_type": cert.track_type,
                "enterprise_name": cert.enterprise_name,
                "started_at": cert.started_at,
                "completed_at": cert.completed_at,
                "score": cert.score,
                "total_questions": cert.total_questions,
                "passed": cert.passed,
                "issue_date": cert.issue_date,
                "verification_hash": cert.verification_hash,
                "template_snapshot": cert.template_snapshot,
            },
            message="Certificate is authentic and verified in the official Sifo Drive National Registry.",
        )
