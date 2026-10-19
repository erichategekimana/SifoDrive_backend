import json
import os
from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.accounts.constants import UserRole
from apps.core.mixins import SuccessResponseMixin
from apps.core.pagination import StandardResultsPagination
from apps.core.permissions import IsAdminLevel
from apps.examinations.serializers import AdminQuizQuestionSerializer
from apps.lms.models import QuizQuestion

SETTINGS_FILE = os.path.join(settings.BASE_DIR, "data", "system_settings.json")


def get_question_bank_edit_access() -> dict:
    """
    Retrieve question bank edit access toggle state.
    Defaults to False (locked/protected) until explicitly turned on by System Admin.
    """
    default_state = {
        "edit_access_enabled": False,
        "updated_at": None,
        "updated_by": None,
    }
    if not os.path.exists(SETTINGS_FILE):
        return default_state
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return {
                "edit_access_enabled": bool(data.get("question_bank_edit_access", False)),
                "updated_at": data.get("question_bank_edit_updated_at"),
                "updated_by": data.get("question_bank_edit_updated_by"),
            }
    except Exception:
        return default_state


def set_question_bank_edit_access(enabled: bool, updated_by_name: str) -> dict:
    """
    Persist question bank edit access toggle state to system settings storage.
    """
    data = {}
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
    data["question_bank_edit_access"] = enabled
    data["question_bank_edit_updated_at"] = timezone.now().isoformat()
    data["question_bank_edit_updated_by"] = updated_by_name
    os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return {
        "edit_access_enabled": enabled,
        "updated_at": data["question_bank_edit_updated_at"],
        "updated_by": data["question_bank_edit_updated_by"],
    }


class AdminQuestionBankEditAccessView(SuccessResponseMixin, APIView):
    """
    Manage question bank editing authorization toggle.
    - GET: Accessible by IsAdminLevel (SYSTEM_ADMIN and TRAINING_ADMIN) to read status.
    - POST: Restricted strictly to SYSTEM_ADMIN.
    """
    permission_classes = [IsAuthenticated, IsAdminLevel]

    def get(self, request):
        cfg = get_question_bank_edit_access()
        is_sys_admin = getattr(request.user, "role", None) == UserRole.SYSTEM_ADMIN
        return self.success_response(
            data={
                "edit_access_enabled": cfg["edit_access_enabled"],
                "updated_at": cfg["updated_at"],
                "updated_by": cfg["updated_by"],
                "can_manage_toggle": is_sys_admin,
            },
            message="Question bank edit access status retrieved.",
        )

    def post(self, request):
        if getattr(request.user, "role", None) != UserRole.SYSTEM_ADMIN:
            return self.error_response(
                code="FORBIDDEN_ROLE",
                message="Only System Administrators are authorized to toggle Question Bank edit access.",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        enabled = request.data.get("edit_access_enabled")
        if enabled is None:
            current = get_question_bank_edit_access()
            enabled = not current["edit_access_enabled"]
        else:
            enabled = bool(enabled)

        updater_name = (
            getattr(request.user, "full_name", None)
            or getattr(request.user, "phone_number", None)
            or "System Admin"
        )
        updated_cfg = set_question_bank_edit_access(enabled, updater_name)
        action_word = "enabled" if enabled else "locked"

        return self.success_response(
            data={
                "edit_access_enabled": updated_cfg["edit_access_enabled"],
                "updated_at": updated_cfg["updated_at"],
                "updated_by": updated_cfg["updated_by"],
                "can_manage_toggle": True,
            },
            message=f"Central Question Bank edit access has been {action_word}.",
        )


class AdminQuestionBankListView(SuccessResponseMixin, generics.ListCreateAPIView):
    """
    Search questions in the Central Question Bank.
    Filter by domain, or search by keyword / question number across Kinyarwanda, English, and French.
    New questions cannot be added directly to the restricted bank.
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
                    | Q(question_text_french__icontains=search_clean)
                    | Q(explanation_kinyarwanda__icontains=search_clean)
                    | Q(explanation__icontains=search_clean)
                    | Q(explanation_french__icontains=search_clean)
                    | Q(option_a_kinyarwanda__icontains=search_clean)
                    | Q(option_b_kinyarwanda__icontains=search_clean)
                    | Q(option_c_kinyarwanda__icontains=search_clean)
                    | Q(option_d_kinyarwanda__icontains=search_clean)
                    | Q(option_a__icontains=search_clean)
                    | Q(option_b__icontains=search_clean)
                    | Q(option_c__icontains=search_clean)
                    | Q(option_d__icontains=search_clean)
                    | Q(option_a_french__icontains=search_clean)
                    | Q(option_b_french__icontains=search_clean)
                    | Q(option_c_french__icontains=search_clean)
                    | Q(option_d_french__icontains=search_clean)
                )

        return qs

    def create(self, request, *args, **kwargs):
        return self.error_response(
            code="RESTRICTED_BANK",
            message="Questions cannot be added to the Central Question Bank.",
            status_code=status.HTTP_403_FORBIDDEN,
        )


class AdminQuestionBankDetailView(SuccessResponseMixin, generics.RetrieveUpdateDestroyAPIView):
    """
    Inspect or edit a question in the Question Bank.
    Editing is allowed for System Admin and Training Admin ONLY when edit access is toggled ON by System Admin.
    Deletions are forbidden on this restricted official repository.
    """
    permission_classes = [IsAuthenticated, IsAdminLevel]
    serializer_class = AdminQuizQuestionSerializer
    queryset = QuizQuestion.objects.filter(is_deleted=False)

    def update(self, request, *args, **kwargs):
        cfg = get_question_bank_edit_access()
        if not cfg["edit_access_enabled"]:
            return self.error_response(
                code="EDIT_ACCESS_LOCKED",
                message="Central Question Bank editing is currently locked by the System Administrator.",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        response = super().update(request, *args, **kwargs)
        if response.status_code in [status.HTTP_200_OK, status.HTTP_201_CREATED]:
            from apps.examinations.services.question_audit_service import record_question_edit
            user = request.user
            editor_name = (
                getattr(user, "full_name", None)
                or getattr(user, "phone_number", None)
                or "Administrator"
            )
            editor_role = getattr(user, "role", "SYSTEM_ADMIN")
            edit_reason = (
                request.data.get("edit_reason", "").strip()
                or "Question prompts, options, or explanations revised."
            )
            instance = self.get_object()
            record_question_edit(instance.id, editor_name, editor_role, edit_reason)
            serializer = self.get_serializer(instance)
            return self.success_response(
                data=serializer.data,
                message="Question updated and revision audit logged.",
            )
        return response

    def partial_update(self, request, *args, **kwargs):
        cfg = get_question_bank_edit_access()
        if not cfg["edit_access_enabled"]:
            return self.error_response(
                code="EDIT_ACCESS_LOCKED",
                message="Central Question Bank editing is currently locked by the System Administrator.",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        response = super().partial_update(request, *args, **kwargs)
        if response.status_code in [status.HTTP_200_OK, status.HTTP_201_CREATED]:
            from apps.examinations.services.question_audit_service import record_question_edit
            user = request.user
            editor_name = (
                getattr(user, "full_name", None)
                or getattr(user, "phone_number", None)
                or "Administrator"
            )
            editor_role = getattr(user, "role", "SYSTEM_ADMIN")
            edit_reason = (
                request.data.get("edit_reason", "").strip()
                or "Question prompts, options, or explanations revised."
            )
            instance = self.get_object()
            record_question_edit(instance.id, editor_name, editor_role, edit_reason)
            serializer = self.get_serializer(instance)
            return self.success_response(
                data=serializer.data,
                message="Question updated and revision audit logged.",
            )
        return response

    def destroy(self, request, *args, **kwargs):
        return self.error_response(
            code="RESTRICTED_BANK",
            message="Questions cannot be deleted from the Central Question Bank.",
            status_code=status.HTTP_403_FORBIDDEN,
        )
