"""
apps/examinations/views/__init__.py
===================================
Facade exposing all examination views.
"""

from apps.examinations.views.candidate_views import (
    CandidateSessionAnswerView,
    CandidateSessionDetailView,
    CandidateSessionProctorEventView,
    CandidateSessionResultsView,
    CandidateSessionSubmitView,
    PublicExamBuyView,
    PublicExamCreditsView,
    PublicExamPackagesView,
    PublicExamStartView,
    StudentExamListView,
    StudentExamStartView,
)
from apps.examinations.views.certificate_views import (
    AdminCertificateDetailView,
    AdminCertificateListView,
    AdminCertificateTemplateDetailView,
    AdminCertificateTemplateListView,
    PublicCertificateVerifyView,
)
from apps.examinations.views.exam_views import (
    AdminExamAuditView,
    AdminExamDetailView,
    AdminExamListView,
    AdminExamTogglePublishView,
)
from apps.examinations.views.question_views import (
    AdminQuestionBankDetailView,
    AdminQuestionBankEditAccessView,
    AdminQuestionBankListView,
)
from apps.examinations.views.session_views import (
    AdminExamPublishView,
    AdminExamSessionDetailView,
    AdminExamSessionListView,
    AdminExamStageActionView,
)

__all__ = [
    "AdminExamListView",
    "AdminExamDetailView",
    "AdminExamAuditView",
    "AdminExamTogglePublishView",
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
    "AdminQuestionBankEditAccessView",
    "AdminQuestionBankDetailView",
    "StudentExamListView",
    "StudentExamStartView",
    "CandidateSessionDetailView",
    "CandidateSessionAnswerView",
    "CandidateSessionProctorEventView",
    "CandidateSessionSubmitView",
    "CandidateSessionResultsView",
    "PublicExamPackagesView",
    "PublicExamCreditsView",
    "PublicExamBuyView",
    "PublicExamStartView",
]

