"""
apps/lms/management/commands/import_question_bank.py
===================================================
Management command to import parsed driving theory questions
from data/parsed_questions.json into the PostgreSQL QuizQuestion table.
"""

import json
import os
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from apps.lms.models import QuizQuestion, QuizDomain, Difficulty, CorrectOption


class Command(BaseCommand):
    help = "Import parsed driving questions into PostgreSQL Question Bank"

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            type=str,
            default="data/parsed_questions.json",
            help="Path to the parsed questions JSON file (relative to project root)",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete existing quiz questions before importing",
        )

    def handle(self, *args, **options):
        json_rel_path = options["file"]
        clear_first = options["clear"]

        json_path = os.path.join(settings.BASE_DIR, json_rel_path)

        if not os.path.exists(json_path):
            self.stderr.write(self.style.ERROR(f"File not found: {json_path}"))
            return

        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.stdout.write(f"Loaded {len(data)} questions from {json_rel_path}")

        created_count = 0
        updated_count = 0

        with transaction.atomic():
            if clear_first:
                count_deleted, _ = QuizQuestion.objects.all().delete()
                self.stdout.write(self.style.WARNING(f"Cleared {count_deleted} existing questions."))

            for item in data:
                q_num = item.get("question_number")
                domain = item.get("domain", QuizDomain.SAFETY)
                if domain not in QuizDomain.values:
                    domain = QuizDomain.SAFETY

                correct = (item.get("correct_option") or "A").upper()
                if correct not in CorrectOption.values:
                    correct = "A"

                defaults = {
                    "domain": domain,
                    "difficulty": Difficulty.MEDIUM,
                    "question_text_kinyarwanda": item.get("question_text_kinyarwanda", "").strip(),
                    "question_text": item.get("question_text", "").strip(),
                    "option_a_kinyarwanda": item.get("option_a_kinyarwanda", "").strip()[:500],
                    "option_b_kinyarwanda": item.get("option_b_kinyarwanda", "").strip()[:500],
                    "option_c_kinyarwanda": item.get("option_c_kinyarwanda", "").strip()[:500],
                    "option_d_kinyarwanda": item.get("option_d_kinyarwanda", "").strip()[:500],
                    "option_a": item.get("option_a", "").strip()[:500],
                    "option_b": item.get("option_b", "").strip()[:500],
                    "option_c": item.get("option_c", "").strip()[:500],
                    "option_d": item.get("option_d", "").strip()[:500],
                    "correct_option": correct,
                    "explanation": item.get("explanation", "").strip(),
                    "explanation_kinyarwanda": item.get("explanation_kinyarwanda", "").strip(),
                    "image": item.get("image") or None,
                    "option_a_image": item.get("option_a_image") or None,
                    "option_b_image": item.get("option_b_image") or None,
                    "option_c_image": item.get("option_c_image") or None,
                    "option_d_image": item.get("option_d_image") or None,
                    "is_active": True,
                }

                obj, created = QuizQuestion.objects.update_or_create(
                    question_number=q_num,
                    defaults=defaults,
                )

                if created:
                    created_count += 1
                else:
                    updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully processed question bank: "
                f"{created_count} created, {updated_count} updated. "
                f"Total in PostgreSQL: {QuizQuestion.objects.count()}"
            )
        )
