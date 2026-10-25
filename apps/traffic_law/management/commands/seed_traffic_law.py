#!/usr/bin/env python3
"""
Django Management Command: seed_traffic_law
===========================================
Idempotently loads and synchronizes the entire Rwanda Traffic Law digital corpus:
- 161 Statutory Articles (Ingingo 1 to 159 + 47 bis + 56 bis)
- 43 Statutory Definitions (Article 2)
- 64 Official Road Signs with visual crops
- 16 Road Surface Markings with visual crops
- 220 Police Magazine Evaluation Q&As with article cross-references
- 401 Companion Theory Exam Questions with trilingual options & diagrams

Usage:
    python manage.py seed_traffic_law
    python manage.py seed_traffic_law --force
    python manage.py seed_traffic_law --skip-images
"""

import os
import json
import shutil
from pathlib import Path
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.conf import settings

from apps.traffic_law.models import (
    TrafficLawArticle,
    TrafficLawDefinition,
    TrafficSign,
    RoadMarking,
    PoliceEvaluationQuestion,
    TrafficQuestion,
)


class Command(BaseCommand):
    help = "Seed Rwanda Traffic Law (Presidential Order No. 85/01) data into database"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Clear existing traffic law records before seeding",
        )
        parser.add_argument(
            "--skip-images",
            action="store_true",
            help="Skip copying visual assets to MEDIA_ROOT",
        )
        parser.add_argument(
            "--quiet",
            action="store_true",
            help="Suppress verbose logging",
        )

    def handle(self, *args, **options):
        force = options["force"]
        skip_images = options["skip_images"]
        quiet = options["quiet"]

        data_dir = Path(settings.BASE_DIR) / "data" / "traffic_law"
        if not data_dir.exists():
            self.stderr.write(self.style.ERROR(f"Data directory not found at: {data_dir}"))
            return

        media_root = Path(settings.MEDIA_ROOT)
        signs_media_dir = media_root / "traffic_law" / "signs"
        markings_media_dir = media_root / "traffic_law" / "markings"
        questions_media_dir = media_root / "traffic_law" / "questions"

        if not skip_images:
            signs_media_dir.mkdir(parents=True, exist_ok=True)
            markings_media_dir.mkdir(parents=True, exist_ok=True)
            questions_media_dir.mkdir(parents=True, exist_ok=True)

        if not quiet:
            self.stdout.write(self.style.MIGRATE_HEADING("=" * 75))
            self.stdout.write(self.style.MIGRATE_HEADING("SEEDING RWANDA TRAFFIC LAW CORPUS (IGAZETI N° 85/01)"))
            self.stdout.write(self.style.MIGRATE_HEADING("=" * 75))

        with transaction.atomic():
            if force:
                if not quiet:
                    self.stdout.write(self.style.WARNING("Clearing existing traffic law records..."))
                TrafficQuestion.objects.all().delete()
                PoliceEvaluationQuestion.objects.all().delete()
                RoadMarking.objects.all().delete()
                TrafficSign.objects.all().delete()
                TrafficLawDefinition.objects.all().delete()
                TrafficLawArticle.objects.all().delete()

            # -------------------------------------------------------------
            # 1. Seed TrafficLawArticles (161 articles)
            # -------------------------------------------------------------
            articles_file = data_dir / "articles.json"
            with open(articles_file, "r", encoding="utf-8") as f:
                articles_data = json.load(f)
            articles_list = articles_data.get("articles", [])

            article_map = {}  # Decimal(number) -> instance
            article_id_map = {}  # "art_1" -> instance

            for art in articles_list:
                num = Decimal(str(art["article_number"]))
                is_bis = num in (Decimal("47.1"), Decimal("56.1"))
                
                obj, created = TrafficLawArticle.objects.update_or_create(
                    article_number=num,
                    defaults={
                        "article_code": art["article_id"],
                        "article_label": art["article_label"],
                        "part_number": art.get("part_number_int", 1),
                        "part_roman": art.get("part_roman", "I"),
                        "part_title": art.get("part_title", ""),
                        "chapter_number": art.get("chapter_number", ""),
                        "chapter_title": art.get("chapter_title", ""),
                        "section_number": art.get("section_number", ""),
                        "section_title": art.get("section_title", ""),
                        "title": art.get("title", ""),
                        "content": art.get("content", ""),
                        "word_count": art.get("word_count", 0),
                        "key_values": art.get("key_values", {}),
                        "source_page": art.get("source_page"),
                        "is_bis": is_bis,
                    },
                )
                article_map[num] = obj
                article_id_map[art["article_id"]] = obj

            if not quiet:
                self.stdout.write(self.style.SUCCESS(f"✓ Articles: {len(article_map)} statutory articles seeded"))

            # -------------------------------------------------------------
            # 2. Seed TrafficLawDefinitions (43 definitions)
            # -------------------------------------------------------------
            definitions_file = data_dir / "definitions.json"
            with open(definitions_file, "r", encoding="utf-8") as f:
                definitions_list = json.load(f)

            art2_obj = article_map.get(Decimal("2.0"))

            for d in definitions_list:
                TrafficLawDefinition.objects.update_or_create(
                    number=d["number"],
                    defaults={
                        "term_rw": d.get("term", ""),
                        "term_fr": d.get("term_fr", ""),
                        "term_en": d.get("term_en", ""),
                        "definition_rw": d.get("definition", ""),
                        "definition_fr": d.get("definition_fr", ""),
                        "definition_en": d.get("definition_en", ""),
                        "article": art2_obj,
                    },
                )

            if not quiet:
                self.stdout.write(self.style.SUCCESS(f"✓ Definitions: {len(definitions_list)} definitions seeded (linked to Art 2)"))

            # -------------------------------------------------------------
            # 3. Seed TrafficSigns (64 signs)
            # -------------------------------------------------------------
            signs_file = data_dir / "signs_catalog.json"
            with open(signs_file, "r", encoding="utf-8") as f:
                signs_list = json.load(f)

            signs_assets_dir = data_dir / "assets" / "signs"

            for s in signs_list:
                code = s["code"]
                img_name = s.get("image_filename") or f"sign_{code.replace('.', '_')}.png"
                rel_media_path = f"traffic_law/signs/{img_name}"

                if not skip_images and signs_assets_dir.exists():
                    src_img = signs_assets_dir / img_name
                    dst_img = signs_media_dir / img_name
                    if src_img.exists() and not dst_img.exists():
                        shutil.copy2(src_img, dst_img)

                sign_obj, _ = TrafficSign.objects.update_or_create(
                    code=code,
                    defaults={
                        "category": s.get("category", "WARNING"),
                        "name_rw": s.get("name_rw", ""),
                        "name_fr": s.get("name_fr", ""),
                        "name_en": s.get("name_en", ""),
                        "description_rw": s.get("description_rw", ""),
                        "description_fr": s.get("description_fr", ""),
                        "description_en": s.get("description_en", ""),
                        "image": rel_media_path,
                        "image_path": rel_media_path,
                        "source_page": s.get("page"),
                        "crop_box": s.get("crop_box", []),
                    },
                )
                # Link related signs articles (Arts 91 to 109)
                for art_n in range(91, 110):
                    if Decimal(str(art_n)) in article_map:
                        sign_obj.related_articles.add(article_map[Decimal(str(art_n))])

            if not quiet:
                self.stdout.write(self.style.SUCCESS(f"✓ Traffic Signs: {len(signs_list)} signs seeded with visual assets"))

            # -------------------------------------------------------------
            # 4. Seed RoadMarkings (16 markings)
            # -------------------------------------------------------------
            markings_file = data_dir / "markings_catalog.json"
            with open(markings_file, "r", encoding="utf-8") as f:
                markings_list = json.load(f)

            markings_assets_dir = data_dir / "assets" / "markings"

            for m in markings_list:
                code = m["article"]
                img_name = m.get("image_filename") or f"marking_{code.replace('.', '_')}.png"
                rel_media_path = f"traffic_law/markings/{img_name}"

                if not skip_images and markings_assets_dir.exists():
                    src_img = markings_assets_dir / img_name
                    dst_img = markings_media_dir / img_name
                    if src_img.exists() and not dst_img.exists():
                        shutil.copy2(src_img, dst_img)

                marking_obj, _ = RoadMarking.objects.update_or_create(
                    marking_code=code,
                    defaults={
                        "name_rw": m.get("name_rw", ""),
                        "name_fr": m.get("name_fr", ""),
                        "name_en": m.get("name_en", ""),
                        "rule_rw": m.get("rule_rw", ""),
                        "rule_fr": m.get("rule_fr", ""),
                        "rule_en": m.get("rule_en", ""),
                        "image": rel_media_path,
                        "image_path": rel_media_path,
                        "source_page": m.get("page"),
                    },
                )
                # Link related markings articles (Arts 110 to 118)
                for art_n in range(110, 119):
                    if Decimal(str(art_n)) in article_map:
                        marking_obj.related_articles.add(article_map[Decimal(str(art_n))])

            if not quiet:
                self.stdout.write(self.style.SUCCESS(f"✓ Road Markings: {len(markings_list)} markings seeded with visual assets"))

            # -------------------------------------------------------------
            # 5. Seed PoliceEvaluationQuestions (220 questions)
            # -------------------------------------------------------------
            evals_file = data_dir / "police_magazine_evaluations.json"
            with open(evals_file, "r", encoding="utf-8") as f:
                evals_list = json.load(f)

            for ev in evals_list:
                q_num = ev["question_number"]
                ev_obj, _ = PoliceEvaluationQuestion.objects.update_or_create(
                    question_number=q_num,
                    defaults={
                        "question_rw": ev.get("question", ""),
                        "answer_rw": ev.get("answer", ""),
                        "source_page": ev.get("source_page", 89),
                    },
                )
                # Link related statutory articles
                for art_n in ev.get("related_articles", []):
                    dec_n = Decimal(str(art_n))
                    if dec_n in article_map:
                        ev_obj.related_articles.add(article_map[dec_n])

            if not quiet:
                self.stdout.write(self.style.SUCCESS(f"✓ Police Evaluations: {len(evals_list)} Q&As seeded with cross-references"))

            # -------------------------------------------------------------
            # 6. Seed TrafficQuestions (401 questions)
            # -------------------------------------------------------------
            questions_file = data_dir / "questions_bank.json"
            with open(questions_file, "r", encoding="utf-8") as f:
                questions_list = json.load(f)

            q_assets_dir = data_dir / "assets" / "questions"

            for q in questions_list:
                q_num = q["question_number"]
                q_text = q.get("question_text", {})
                exp_text = q.get("explanation", {})

                img_field = ""
                img_path = q.get("image_path", "")
                if img_path:
                    img_filename = Path(img_path).name
                    img_field = f"traffic_law/questions/{img_filename}"
                    if not skip_images and q_assets_dir.exists():
                        src_img = q_assets_dir / img_filename
                        dst_img = questions_media_dir / img_filename
                        if src_img.exists() and not dst_img.exists():
                            shutil.copy2(src_img, dst_img)

                q_obj, _ = TrafficQuestion.objects.update_or_create(
                    question_number=q_num,
                    defaults={
                        "question_text_rw": q_text.get("kinyarwanda", ""),
                        "question_text_en": q_text.get("english", ""),
                        "question_text_fr": q_text.get("french", ""),
                        "options": q.get("options", {}),
                        "correct_choice": q.get("correct_answer", ""),
                        "explanation_rw": exp_text.get("kinyarwanda", ""),
                        "explanation_en": exp_text.get("english", ""),
                        "explanation_fr": exp_text.get("french", ""),
                        "image": img_field,
                        "image_path": img_field,
                        "domain_tags": q.get("domain_tags", []),
                        "source_page": q.get("source_page"),
                    },
                )

            if not quiet:
                self.stdout.write(self.style.SUCCESS(f"✓ Companion Question Bank: {len(questions_list)} questions seeded"))
                self.stdout.write(self.style.MIGRATE_HEADING("=" * 75))
                self.stdout.write(self.style.SUCCESS("ALL RWANDA TRAFFIC LAW DATASETS SUCCESSFULLY SEEDED!"))
                self.stdout.write(self.style.MIGRATE_HEADING("=" * 75))
