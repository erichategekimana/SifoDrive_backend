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
    AdminExamAuditView,
    AdminExamDetailView,
    AdminExamListView,
    AdminExamPublishView,
    AdminExamSessionDetailView,
    AdminExamSessionListView,
    AdminExamStageActionView,
    AdminExamTogglePublishView,
    AdminQuestionBankDetailView,
    AdminQuestionBankEditAccessView,
    AdminQuestionBankListView,
    CandidateSessionAnswerView,
    CandidateSessionDetailView,
    CandidateSessionProctorEventView,
    CandidateSessionResultsView,
    CandidateSessionSubmitView,
    PublicCertificateVerifyView,
    PublicExamBuyView,
    PublicExamCreditsView,
    PublicExamHistoryView,
    PublicExamOTPRequestView,
    PublicExamOTPVerifyView,
    PublicExamPackagesView,
    PublicExamPaymentStatusView,
    PublicExamStartView,
    StudentExamListView,
    StudentExamStartView,
)

app_name = "examinations"

urlpatterns = [
    # ── Official Examination Windows (Independent of Quizzes) ───────────────
    path("admin/exams/", AdminExamListView.as_view(), name="admin_exams_list"),
    path("admin/exams/<str:pk_or_type>/audit/", AdminExamAuditView.as_view(), name="admin_exam_audit"),
    path("admin/exams/<uuid:pk>/", AdminExamDetailView.as_view(), name="admin_exam_detail"),
    path("admin/exams/<uuid:pk>/toggle-publish/", AdminExamTogglePublishView.as_view(), name="admin_exam_toggle_publish"),
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
    path("admin/questions/edit-access/", AdminQuestionBankEditAccessView.as_view(), name="admin_question_edit_access"),
    path("admin/questions/<uuid:pk>/", AdminQuestionBankDetailView.as_view(), name="admin_question_detail"),

    # ── Student Scheduled Examination Endpoints ─────────────────────────────
    path("student/exams/", StudentExamListView.as_view(), name="student_exams_list"),
    path("student/exams/<uuid:exam_id>/start/", StudentExamStartView.as_view(), name="student_exam_start"),

    # ── Candidate Active Session Execution & Proctoring (Shared) ───────────
    path("sessions/<uuid:session_id>/", CandidateSessionDetailView.as_view(), name="candidate_session_detail"),
    path("sessions/<uuid:session_id>/answer/", CandidateSessionAnswerView.as_view(), name="candidate_session_answer"),
    path("sessions/<uuid:session_id>/proctor-event/", CandidateSessionProctorEventView.as_view(), name="candidate_session_proctor_event"),
    path("sessions/<uuid:session_id>/submit/", CandidateSessionSubmitView.as_view(), name="candidate_session_submit"),
    path("sessions/<uuid:session_id>/results/", CandidateSessionResultsView.as_view(), name="candidate_session_results"),

    # ── Guest & Public Paid Examination Endpoints ───────────────────────────
    path("public/packages/", PublicExamPackagesView.as_view(), name="public_exam_packages"),
    path("public/credits/", PublicExamCreditsView.as_view(), name="public_exam_credits"),
    path("public/history/", PublicExamHistoryView.as_view(), name="public_exam_history"),
    path("public/otp/request/", PublicExamOTPRequestView.as_view(), name="public_exam_otp_request"),
    path("public/otp/verify/", PublicExamOTPVerifyView.as_view(), name="public_exam_otp_verify"),
    path("public/buy/", PublicExamBuyView.as_view(), name="public_exam_buy"),
    path("public/payment-status/<uuid:reference_id>/", PublicExamPaymentStatusView.as_view(), name="public_exam_payment_status"),
    path("public/start/", PublicExamStartView.as_view(), name="public_exam_start"),
]

