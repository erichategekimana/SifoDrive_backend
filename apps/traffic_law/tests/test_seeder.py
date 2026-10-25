from decimal import Decimal
from django.test import TestCase
from django.core.management import call_command

from apps.traffic_law.models import (
    TrafficLawArticle,
    TrafficLawDefinition,
    TrafficSign,
    RoadMarking,
    PoliceEvaluationQuestion,
    TrafficQuestion,
    SignCategory,
)


class TrafficLawSeederTestCase(TestCase):
    """
    Tests the seed_traffic_law management command for data completeness,
    statutory integrity, cross-referencing, and idempotency.
    """

    def test_seed_traffic_law_completeness_and_idempotency(self):
        # 1. First Run: Seed database
        call_command("seed_traffic_law", skip_images=True, quiet=True)

        # Assert exact counts
        self.assertEqual(TrafficLawArticle.objects.count(), 161)
        self.assertEqual(TrafficLawDefinition.objects.count(), 43)
        self.assertEqual(TrafficSign.objects.count(), 64)
        self.assertEqual(RoadMarking.objects.count(), 16)
        self.assertEqual(PoliceEvaluationQuestion.objects.count(), 220)
        self.assertEqual(TrafficQuestion.objects.count(), 401)

        # Assert sequential continuity of articles
        articles = list(TrafficLawArticle.objects.order_by("article_number"))
        art_nums = [float(a.article_number) for a in articles]
        expected_nums = [float(i) for i in range(1, 160)] + [47.1, 56.1]
        expected_nums.sort()
        self.assertEqual(art_nums, expected_nums)

        # Assert bis articles
        art47_bis = TrafficLawArticle.objects.get(article_number=Decimal("47.1"))
        self.assertTrue(art47_bis.is_bis)
        self.assertEqual(art47_bis.article_code, "art_47_bis")
        self.assertIn("Imikandara", art47_bis.title)

        art56_bis = TrafficLawArticle.objects.get(article_number=Decimal("56.1"))
        self.assertTrue(art56_bis.is_bis)
        self.assertEqual(art56_bis.article_code, "art_56_bis")

        # Assert key numeric values in articles
        art27 = TrafficLawArticle.objects.get(article_number=Decimal("27.0"))
        self.assertEqual(art27.key_values.get("light_vehicles_kmh"), 80)
        self.assertEqual(art27.key_values.get("agricultural_machinery_kmh"), 25)

        art67 = TrafficLawArticle.objects.get(article_number=Decimal("67.0"))
        self.assertEqual(art67.key_values.get("single_axle_national_roads_t"), 10)
        self.assertEqual(art67.key_values.get("absolute_max_gross_weight_t"), 53)

        art142 = TrafficLawArticle.objects.get(article_number=Decimal("142.0"))
        self.assertIn("Buri mezi atandatu", art142.content)

        art152 = TrafficLawArticle.objects.get(article_number=Decimal("152.0"))
        self.assertIn("amasaha 48", art152.content)

        # Assert definition relation to Article 2
        art2 = TrafficLawArticle.objects.get(article_number=Decimal("2.0"))
        def1 = TrafficLawDefinition.objects.get(number=1)
        self.assertEqual(def1.article, art2)
        self.assertEqual(def1.term_rw, "Inzira Nyabagendwa")
        self.assertEqual(def1.term_fr, "Voie publique")

        # Assert sign category & related articles
        sign_a1a = TrafficSign.objects.get(code="A.1a")
        self.assertEqual(sign_a1a.category, SignCategory.WARNING)
        self.assertTrue(sign_a1a.related_articles.exists())

        # Assert marking rule & related articles
        marking_110_2 = RoadMarking.objects.get(marking_code="110.2")
        self.assertIn("Umuyobozi wese abujijwe kuwurenga", marking_110_2.rule_rw)
        self.assertTrue(marking_110_2.related_articles.exists())

        # Assert police evaluation cross references
        eval1 = PoliceEvaluationQuestion.objects.get(question_number=1)
        self.assertTrue(eval1.related_articles.filter(article_number=Decimal("91.0")).exists())

        # Assert question bank
        q1 = TrafficQuestion.objects.get(question_number=1)
        self.assertIn("a", q1.options)
        self.assertTrue(bool(q1.question_text_rw))

        # 2. Second Run: Test Idempotency (Must not duplicate or error)
        call_command("seed_traffic_law", skip_images=True, quiet=True)

        self.assertEqual(TrafficLawArticle.objects.count(), 161)
        self.assertEqual(TrafficLawDefinition.objects.count(), 43)
        self.assertEqual(TrafficSign.objects.count(), 64)
        self.assertEqual(RoadMarking.objects.count(), 16)
        self.assertEqual(PoliceEvaluationQuestion.objects.count(), 220)
        self.assertEqual(TrafficQuestion.objects.count(), 401)
