"""
apps/examinations/urls.py
=========================
URL routes for examinations, review pipeline, certificates, and question bank editor.
"""

from django.urls import path
from apps.examinations.views import (
    AdminCertificateDetailView,
    AdminCertificateListView,
    AdminCertificateTemplateDetailView,
    AdminCertificateTemplateListView,
    AdminExamPublishView,
    AdminExamSessionDetailView,
    AdminExamSessionListView,
    AdminExamStageActionView,
    AdminQuestionBankDetailView,
    AdminQuestionBankListView,
    PublicCertificateVerifyView,
)

app_name = "examinations"

urlpatterns = [
    # ── Admin Examination Sessions & Review Pipeline ────────────────────────
    path("admin/sessions/", AdminExamSessionListView.as_view(), name="admin_sessions_list"),
    path("admin/sessions/<uuid:pk>/", AdminExamSessionDetailView.as_view(), name="admin_session_detail"),
    path("admin/sessions/<uuid:session_id>/action/", AdminExamStageActionView.as_view(), name="admin_session_action"),
    path("admin/sessions/publish/", AdminExamPublishView.as_view(), name="admin_sessions_publish"),

    # ── Certificates Registry & Template Customizer ─────────────────────────
    path("admin/certificates/", AdminCertificateListView.as_view(), name="admin_certificates_list"),
    path("admin/certificates/<uuid:pk>/", AdminCertificateDetailView.as_view(), name="admin_certificate_detail"),
    path("admin/templates/", AdminCertificateTemplateListView.as_view(), name="admin_templates_list"),
    path("admin/templates/<uuid:pk>/", AdminCertificateTemplateDetailView.as_view(), name="admin_template_detail"),

    # ── Public QR Code Verification ─────────────────────────────────────────
    path("verify/<str:hash_or_code>/", PublicCertificateVerifyView.as_view(), name="public_certificate_verify"),

    # ── Question Bank Studio (LMS Quiz Questions) ───────────────────────────
    path("admin/questions/", AdminQuestionBankListView.as_view(), name="admin_questions_list"),
    path("admin/questions/<uuid:pk>/", AdminQuestionBankDetailView.as_view(), name="admin_question_detail"),
]
