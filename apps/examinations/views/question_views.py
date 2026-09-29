from django.db.models import Q
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from apps.core.mixins import SuccessResponseMixin
from apps.core.pagination import StandardResultsPagination
from apps.core.permissions import IsAdminLevel
from apps.examinations.serializers import AdminQuizQuestionSerializer
from apps.lms.models import QuizQuestion


class AdminQuestionBankListView(SuccessResponseMixin, generics.ListCreateAPIView):
    """
    Search and manage questions in the Question Bank.
    Filter by domain, difficulty, or search by keyword / question number.
    """
    permission_classes = [IsAuthenticated, IsAdminLevel]
    serializer_class = AdminQuizQuestionSerializer
    pagination_class = StandardResultsPagination

    def get_queryset(self):
        qs = QuizQuestion.objects.filter(is_deleted=False).order_by("question_number", "id")

        domain = self.request.query_params.get("domain")
        if domain and domain.upper() != "ALL":
            qs = qs.filter(domain=domain.upper())

        search = self.request.query_params.get("search")
        if search:
            search_clean = search.strip()
            if search_clean.isdigit():
                qs = qs.filter(question_number=int(search_clean))
            else:
                qs = qs.filter(
                    Q(question_text_kinyarwanda__icontains=search_clean)
                    | Q(question_text__icontains=search_clean)
                    | Q(explanation_kinyarwanda__icontains=search_clean)
                    | Q(explanation__icontains=search_clean)
                    | Q(option_a_kinyarwanda__icontains=search_clean)
                    | Q(option_b_kinyarwanda__icontains=search_clean)
                    | Q(option_c_kinyarwanda__icontains=search_clean)
                    | Q(option_d_kinyarwanda__icontains=search_clean)
                )

        return qs


class AdminQuestionBankDetailView(SuccessResponseMixin, generics.RetrieveUpdateDestroyAPIView):
    """
    Inspect, edit, or delete a question in the Question Bank.
    Enables correcting typos in English & Kinyarwanda, editing options,
    changing correct answer, diagrams, and explanations.
    """
    permission_classes = [IsAuthenticated, IsAdminLevel]
    serializer_class = AdminQuizQuestionSerializer
    queryset = QuizQuestion.objects.filter(is_deleted=False)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.is_deleted = True
        instance.is_active = False
        instance.save(update_fields=["is_deleted", "is_active", "updated_at"])
        return self.success_response(data=None, message="Question removed from active pool.")
