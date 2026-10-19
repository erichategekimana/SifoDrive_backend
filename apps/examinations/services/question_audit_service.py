import json
import os
from django.conf import settings
from django.utils import timezone

AUDIT_FILE = os.path.join(settings.BASE_DIR, "data", "question_edit_history.json")


def load_all_question_edits() -> dict:
    if not os.path.exists(AUDIT_FILE):
        return {}
    try:
        with open(AUDIT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def get_question_edit_info(question_id: str | None) -> dict | None:
    if not question_id:
        return None
    data = load_all_question_edits()
    return data.get(str(question_id))


def record_question_edit(question_id: str, editor_name: str, editor_role: str, edit_reason: str) -> dict:
    data = load_all_question_edits()
    q_key = str(question_id)
    now_iso = timezone.now().isoformat()
    clean_reason = (edit_reason or "").strip() or "Question prompt, choices, or explanation updated."

    record = {
        "edited_by_name": editor_name,
        "edited_by_role": editor_role,
        "edited_at": now_iso,
        "edit_reason": clean_reason,
    }

    if q_key not in data:
        data[q_key] = {
            "last_edited_by_name": editor_name,
            "last_edited_by_role": editor_role,
            "last_edited_at": now_iso,
            "edit_reason": clean_reason,
            "history": [record],
        }
    else:
        data[q_key]["last_edited_by_name"] = editor_name
        data[q_key]["last_edited_by_role"] = editor_role
        data[q_key]["last_edited_at"] = now_iso
        data[q_key]["edit_reason"] = clean_reason
        history = data[q_key].get("history", [])
        history.insert(0, record)
        data[q_key]["history"] = history

    os.makedirs(os.path.dirname(AUDIT_FILE), exist_ok=True)
    with open(AUDIT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    # Invalidate serializer cache
    from apps.examinations.serializers.question_serializers import AdminQuizQuestionSerializer
    AdminQuizQuestionSerializer._audit_cache = None

    return data[q_key]
