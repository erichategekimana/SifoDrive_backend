"""
apps/examinations/views/__init__.py
===================================
Facade exposing all examination views.
"""

from apps.examinations.views.certificate_views import (
    AdminCertificateDetailView,
    AdminCertificateListView,
    AdminCertificateTemplateDetailView,
    AdminCertificateTemplateListView,
    PublicCertificateVerifyView,
)
from apps.examinations.views.question_views import (
    AdminQuestionBankDetailView,
    AdminQuestionBankListView,
)
from apps.examinations.views.session_views import (
    AdminExamPublishView,
    AdminExamSessionDetailView,
    AdminExamSessionListView,
    AdminExamStageActionView,
)

__all__ = [
    "AdminExamSessionListView",
    "AdminExamSessionDetailView",
    "AdminExamStageActionView",
    "AdminExamPublishView",
    "AdminCertificateListView",
    "AdminCertificateDetailView",
    "AdminCertificateTemplateListView",
    "AdminCertificateTemplateDetailView",
    "PublicCertificateVerifyView",
    "AdminQuestionBankListView",
    "AdminQuestionBankDetailView",
]
