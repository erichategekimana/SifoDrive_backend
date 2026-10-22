"""
apps/examinations/services/exam_service.py
=========================================
Service layer managing official theory Exam entities.
Completely decoupled from LMS quizzes.
Enforces engine constants:
  - 20 questions
  - 20 minutes duration
  - 1 point per question
  - Passing score: 12
"""

import json
import logging
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

EXAMS_FILE = os.path.join(settings.BASE_DIR, "data", "exams.json")


class ExamService:
    """Service providing CRUD and lifecycle operations for official Examinations."""

    @staticmethod
    def _ensure_storage_dir():
        os.makedirs(os.path.dirname(EXAMS_FILE), exist_ok=True)

    STANDARD_EXAMS = [
        {
            "id": "e1111111-1111-4111-8111-111111111111",
            "title": "Sifo Driving School Examination",
            "title_kinyarwanda": "Ikizamini cy'Amategeko y'Umuhanda — Sifo Driving School",
            "title_french": "Examen Théorique de Conduite — Sifo Driving School",
            "exam_type": "STUDENT",
            "status": "PUBLISHED",
            "cohort_id": None,
            "cohort_name": "Curriculum (All Enrolled Students)",
            "open_date": "2026-10-01T08:00:00Z",
            "due_date": "2026-12-31T18:00:00Z",
            "closing_date": "2026-12-31T23:59:59Z",
            "instructions": "Official Sifo Driving School theory examination attached to the driver training curriculum. Proctoring rules are mandatory: live webcam on, microphone monitoring, pre-flight selfie identity check, and tab-switch departure detection. Exactly 1 official attempt per student.",
            "instructions_kinyarwanda": "Iki ni ikizamini cy'amategeko y'umuhanda cy'ishuri ryo gutwara ibinyabiziga rya Sifo gishamikiye ku nteganyanyigisho y'abanyeshuri (curriculum). Kamera na mikoro bigomba kuba bikora, kandi kwambuka amadirishya y'imbuga bizandikwa nk'amakosa. Ufite uburenganzira bwo gukora inshuro 1 gusa.",
            "instructions_french": "Examen théorique de conduite officiel de Sifo Driving School rattaché au cursus de formation. Surveillance obligatoire: caméra, micro, selfie d'identité et détection de changement d'onglet. Une seule tentative autorisée.",
            "rubric": "Total of 20 randomly drawn questions across official domains (Priority: 4, Signage: 4, Speed: 4, Legal: 3, Safety: 3, Parking: 2). Each correct answer awards 1 point. Minimum passing score is 12 points (60%). Auto-graded and forwarded for 3-stage Board, Training Admin, and System Admin certification review.",
            "rubric_kinyarwanda": "Ibibazo 20 biturutse muri banki y'ibibazo (Ubutambike: 4, Ibyapa: 4, Umuvuduko: 4, Amategeko: 3, Umutekano: 3, Guhagarara: 2). Buri gisubizo gifite inota 1 (Amanota yo gutsinda ni 12/20). Isuzumwa rikorwa n'ubuyobozi.",
            "rubric_french": "20 questions tirées aléatoirement. 1 point par question. Note de passage 12/20. Résultats validés par le comité d'audit.",
            "is_published": True,
            "total_questions": 20,
            "duration_minutes": 20,
            "points_per_question": 1,
            "passing_score": 12,
            "created_at": "2026-10-01T08:00:00Z",
            "updated_at": "2026-10-15T08:00:00Z",
            "created_by_name": "Training Director",
            "active_sessions_count": 0,
            "completed_sessions_count": 0,
        },
        {
            "id": "e2222222-2222-4222-8222-222222222222",
            "title": "Public Examination",
            "title_kinyarwanda": "Ikizamini cy'Imyitozo rusange cy'Amategeko y'Umuhanda",
            "title_french": "Examen Blanc Public & Candidats Libres",
            "exam_type": "PUBLIC_PRACTICE",
            "status": "PUBLISHED",
            "cohort_id": None,
            "cohort_name": "Public & Permanent Guests",
            "open_date": "2026-01-01T00:00:00Z",
            "due_date": None,
            "closing_date": None,
            "instructions": "Open examination simulator for guest accounts and public candidates. Users purchase individual exams or discounted bundles via MTN/Airtel MoMo paying number. Fullscreen recommended. System auto-pulls 20 fresh questions across domains. Instant auto-grading and answer review.",
            "instructions_kinyarwanda": "Ikizamini cy'imyitozo rusange kuri buri wese n'abafite konti z'abashyitsi. Wishyura ukoresheje MoMo kuri buri kizamini cyangwa ipaki y'ibizamini. Ibisubizo bihabwa ako kanya ukirangiza.",
            "instructions_french": "Simulateur d'examen ouvert au grand public et invités permanents. Achat à l'unité ou par forfait via MoMo. Correction instantanée avec explications détaillées.",
            "rubric": "Total of 20 randomly drawn questions across official domains (Priority: 4, Signage: 4, Speed: 4, Legal: 3, Safety: 3, Parking: 2). 1 point per question, 12/20 to pass. Auto-graded instantly upon completion and published straight away with complete answer key and explanations in EN, RW, and FR.",
            "rubric_kinyarwanda": "Ibibazo 20 by'amahitamo biturutse muri banki nkuru. Inota 1 kuri buri gisubizo (12/20 yo gutsinda). Ibisobanuro byose bitangwa ako kanya.",
            "rubric_french": "20 questions aléatoires réparties sur les domaines officiels. 12/20 pour réussir. Résultats immédiats avec corrigés et explications.",
            "is_published": True,
            "total_questions": 20,
            "duration_minutes": 20,
            "points_per_question": 1,
            "passing_score": 12,
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-10-15T08:00:00Z",
            "created_by_name": "System Administrator",
            "active_sessions_count": 0,
            "completed_sessions_count": 0,
        },
    ]

    @classmethod
    def load_all_exams(cls) -> List[Dict[str, Any]]:
        cls._ensure_storage_dir()
        loaded = []
        if os.path.exists(EXAMS_FILE):
            try:
                with open(EXAMS_FILE, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
            except Exception as e:
                logger.error("Failed to load exams from %s: %s", EXAMS_FILE, e)
                loaded = []

        # Ensure the two standard exams exist
        existing_types = {e.get("exam_type"): e for e in loaded}
        updated = False
        final_exams = []

        for std in cls.STANDARD_EXAMS:
            st_type = std["exam_type"]
            if st_type in existing_types:
                item = existing_types[st_type]
                # Enforce Sifo Driving School curriculum identity and non-cohort attachment
                if st_type == "STUDENT":
                    if item.get("title") != std["title"] or "National" in item.get("title", "") or "Cohort A" in item.get("title", "") or item.get("cohort_name") != std["cohort_name"]:
                        item["title"] = std["title"]
                        item["title_kinyarwanda"] = std["title_kinyarwanda"]
                        item["title_french"] = std["title_french"]
                        item["cohort_id"] = None
                        item["cohort_name"] = std["cohort_name"]
                        item["instructions"] = std["instructions"]
                        item["instructions_kinyarwanda"] = std["instructions_kinyarwanda"]
                        item["instructions_french"] = std["instructions_french"]
                        item["rubric"] = std["rubric"]
                        item["rubric_kinyarwanda"] = std["rubric_kinyarwanda"]
                        item["rubric_french"] = std["rubric_french"]
                        updated = True
                final_exams.append(item)
            else:
                final_exams.append(std)
                updated = True

        # Keep any other previously created custom exams if needed
        for e in loaded:
            if e.get("exam_type") not in ("STUDENT", "PUBLIC_PRACTICE") and e not in final_exams:
                final_exams.append(e)

        if updated or not os.path.exists(EXAMS_FILE):
            cls.save_all_exams(final_exams)

        return final_exams

    @classmethod
    def save_all_exams(cls, exams: List[Dict[str, Any]]) -> None:
        cls._ensure_storage_dir()
        temp_file = f"{EXAMS_FILE}.tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(exams, f, indent=2, ensure_ascii=False)
        os.replace(temp_file, EXAMS_FILE)

    @classmethod
    def get_exam(cls, exam_id: str) -> Optional[Dict[str, Any]]:
        exams = cls.load_all_exams()
        for e in exams:
            if str(e.get("id")) == str(exam_id):
                return e
        return None

    @classmethod
    def list_exams(
        cls,
        search: Optional[str] = None,
        cohort_id: Optional[str] = None,
        status: Optional[str] = None,
        exam_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        exams = cls.load_all_exams()
        results = []
        search_lower = (search or "").strip().lower()

        for e in exams:
            if cohort_id and cohort_id != "ALL" and str(e.get("cohort_id")) != str(cohort_id):
                continue
            if status and status != "ALL" and e.get("status", "").upper() != status.upper():
                continue
            if exam_type and exam_type != "ALL" and e.get("exam_type", "").upper() != exam_type.upper():
                continue
            if search_lower:
                text_corpus = f"{e.get('title', '')} {e.get('title_kinyarwanda', '')} {e.get('title_french', '')} {e.get('cohort_name', '')} {e.get('instructions', '')}".lower()
                if search_lower not in text_corpus:
                    continue
            results.append(e)

        return sorted(results, key=lambda x: x.get("created_at", ""), reverse=True)

    @classmethod
    def create_exam(cls, data: Dict[str, Any], user: Any) -> Dict[str, Any]:
        """
        Creates an official Exam window.
        Enforces immutable engine defaults: 20 questions, 20 min, 12 passing score.
        """
        now_iso = timezone.now().isoformat()
        exam_id = str(uuid.uuid4())

        user_name = (
            getattr(user, "full_name", None)
            or getattr(user, "phone_number", None)
            or "Training Administrator"
        )

        title = data.get("title", "").strip() or "Official Driving Theory Exam"
        exam_type = data.get("exam_type", "STUDENT")
        is_published = bool(data.get("is_published", False))
        exam_status = "PUBLISHED" if is_published else data.get("status", "DRAFT")

        new_exam = {
            "id": exam_id,
            "title": title,
            "title_kinyarwanda": data.get("title_kinyarwanda", "").strip(),
            "title_french": data.get("title_french", "").strip(),
            "exam_type": exam_type,
            "status": exam_status,
            "cohort_id": str(data.get("cohort_id") or data.get("cohort") or "") or None,
            "cohort_name": data.get("cohort_name", "").strip() or "All Cohorts",
            "open_date": data.get("open_date") or None,
            "due_date": data.get("due_date") or None,
            "closing_date": data.get("closing_date") or None,
            "instructions": data.get("instructions", "").strip(),
            "instructions_kinyarwanda": data.get("instructions_kinyarwanda", "").strip(),
            "instructions_french": data.get("instructions_french", "").strip(),
            "rubric": data.get("rubric", "").strip(),
            "rubric_kinyarwanda": data.get("rubric_kinyarwanda", "").strip(),
            "rubric_french": data.get("rubric_french", "").strip(),
            "is_published": is_published,
            # Immutable engine parameters
            "total_questions": 20,
            "duration_minutes": 20,
            "points_per_question": 1,
            "passing_score": 12,
            "created_at": now_iso,
            "updated_at": now_iso,
            "created_by_name": user_name,
            "active_sessions_count": 0,
            "completed_sessions_count": 0,
        }

        exams = cls.load_all_exams()
        exams.insert(0, new_exam)
        cls.save_all_exams(exams)
        logger.info("Created Exam %s by %s", exam_id, user_name)
        return new_exam

    @classmethod
    def update_exam(cls, exam_id: str, data: Dict[str, Any], user: Any) -> Optional[Dict[str, Any]]:
        exams = cls.load_all_exams()
        for idx, e in enumerate(exams):
            if str(e.get("id")) == str(exam_id):
                # Update allowed schedule and metadata fields
                for field in [
                    "title",
                    "title_kinyarwanda",
                    "title_french",
                    "cohort_id",
                    "cohort_name",
                    "open_date",
                    "due_date",
                    "closing_date",
                    "instructions",
                    "instructions_kinyarwanda",
                    "instructions_french",
                    "rubric",
                    "rubric_kinyarwanda",
                    "rubric_french",
                    "status",
                ]:
                    if field in data:
                        e[field] = data[field]

                if "is_published" in data:
                    e["is_published"] = bool(data["is_published"])
                    if e["is_published"] and e["status"] == "DRAFT":
                        e["status"] = "PUBLISHED"

                # Engine parameters are locked and cannot be overwritten
                e["total_questions"] = 20
                e["duration_minutes"] = 20
                e["points_per_question"] = 1
                e["passing_score"] = 12
                e["updated_at"] = timezone.now().isoformat()

                exams[idx] = e
                cls.save_all_exams(exams)
                return e

        return None

    @classmethod
    def delete_exam(cls, exam_id: str) -> bool:
        exams = cls.load_all_exams()
        initial_len = len(exams)
        exams = [e for e in exams if str(e.get("id")) != str(exam_id)]
        if len(exams) < initial_len:
            cls.save_all_exams(exams)
            return True
        return False

    @classmethod
    def is_public_exam_published(cls) -> bool:
        """Returns True if the public examination engine is currently published."""
        exams = cls.load_all_exams()
        for e in exams:
            if e.get("exam_type") == "PUBLIC_PRACTICE" or str(e.get("id")) == "e2222222-2222-4222-8222-222222222222":
                return bool(e.get("is_published", False))
        return False

    @classmethod
    def toggle_publish(cls, exam_id: str) -> Optional[Dict[str, Any]]:
        exams = cls.load_all_exams()
        for idx, e in enumerate(exams):
            if str(e.get("id")) == str(exam_id):
                current_pub = bool(e.get("is_published", False))
                next_pub = not current_pub
                e["is_published"] = next_pub
                e["status"] = "PUBLISHED" if next_pub else "DRAFT"
                e["updated_at"] = timezone.now().isoformat()
                exams[idx] = e
                cls.save_all_exams(exams)

                # If this is the Public Examination and it was unpublished,
                # automatically deactivate all practice packages in the config.
                if e.get("exam_type") == "PUBLIC_PRACTICE" or str(e.get("id")) == "e2222222-2222-4222-8222-222222222222":
                    try:
                        from apps.examinations.services.credit_service import ExamCreditService
                        if not next_pub:
                            current_pkgs = ExamCreditService._load_packages_config()
                            for pkg in current_pkgs.values():
                                pkg["isActive"] = False
                                pkg["is_active"] = False
                            ExamCreditService.save_packages_config(current_pkgs)
                            logger.info("Public Examination unpublished: automatically deactivated all exam pricing packages.")
                    except Exception as err:
                        logger.error("Failed to sync package deactivation on exam unpublish: %s", err)

                return e
        return None

    @classmethod
    def get_exam_audit_data(cls, exam_id_or_type: str) -> Dict[str, Any]:
        """
        Retrieves detailed audit dossier for the examination:
        - Students / Candidates
        - Attempts count, pass rate, average score
        - MoMo purchases and revenue ledger (for public practice)
        - Proctoring violations, selfies, and review pipeline stages (for student official)
        """
        from apps.examinations.services.credit_service import ExamCreditService
        from apps.examinations.services.engine_service import ExamEngineService

        is_student = (
            exam_id_or_type.lower() in ("student", "students", "cohort", "curriculum")
            or exam_id_or_type == "e1111111-1111-4111-8111-111111111111"
        )

        all_exams = cls.load_all_exams()
        target_exam = None
        for e in all_exams:
            if is_student and e.get("exam_type") == "STUDENT":
                target_exam = e
                break
            elif not is_student and e.get("exam_type") == "PUBLIC_PRACTICE":
                target_exam = e
                break
            elif str(e.get("id")) == str(exam_id_or_type):
                target_exam = e
                is_student = (e.get("exam_type") == "STUDENT")
                break

        if not target_exam:
            target_exam = all_exams[0] if all_exams else {}

        # Fetch sessions
        sessions = ExamEngineService.list_all_sessions(track="STUDENT" if is_student else "PUBLIC")
        total_attempts = len(sessions)
        passed_attempts = sum(1 for s in sessions if s.get("passed") is True)
        scores = [s.get("score") for s in sessions if s.get("score") is not None]
        avg_score = round(sum(scores) / len(scores), 1) if scores else 0
        pass_rate = round((passed_attempts / total_attempts) * 100, 1) if total_attempts > 0 else 0

        total_violations = sum(s.get("violation_count", 0) for s in sessions)
        in_review_count = sum(1 for s in sessions if s.get("status") in ("SUBMITTED", "BOARD_REVIEW", "TRAINING_REVIEW", "SYSTEM_REVIEW"))
        certified_count = sum(1 for s in sessions if s.get("has_certificate") or s.get("certificate_number"))

        # MoMo purchases and revenue for public practice
        transactions = []
        total_revenue_rwf = 0
        total_packages_sold = 0
        if not is_student:
            transactions = ExamCreditService.get_all_transactions()
            total_packages_sold = len(transactions)
            total_revenue_rwf = sum(tx.get("amount_rwf", 0) for tx in transactions)

        return {
            "exam": target_exam,
            "exam_type": "STUDENT" if is_student else "PUBLIC_PRACTICE",
            "kpis": {
                "total_attempts": total_attempts,
                "passed_attempts": passed_attempts,
                "pass_rate_percentage": pass_rate,
                "average_score": avg_score,
                "total_violations": total_violations,
                "in_review_count": in_review_count,
                "certified_count": certified_count,
                "total_packages_sold": total_packages_sold,
                "total_revenue_rwf": total_revenue_rwf,
            },
            "sessions": sessions,
            "transactions": transactions,
            "packages": ExamCreditService.list_packages() if not is_student else [],
        }
