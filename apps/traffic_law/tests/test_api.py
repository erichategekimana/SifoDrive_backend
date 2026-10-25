from rest_framework.test import APITestCase
from rest_framework import status
from django.core.management import call_command
from django.urls import reverse


class TrafficLawAPITestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_traffic_law", skip_images=True, quiet=True)

    def test_summary_stats_endpoint(self):
        url = reverse("api_v1:traffic_law:stats")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        stats = response.data.get("stats", {})
        self.assertEqual(stats.get("total_articles"), 161)
        self.assertEqual(stats.get("total_definitions"), 43)
        self.assertEqual(stats.get("total_traffic_signs"), 64)
        self.assertEqual(stats.get("total_road_markings"), 16)
        self.assertEqual(stats.get("total_police_evaluations"), 220)
        self.assertEqual(stats.get("total_practice_questions"), 401)

    def test_list_articles(self):
        url = reverse("api_v1:traffic_law:article-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Check pagination or results
        count = response.data.get("count") if isinstance(response.data, dict) else len(response.data)
        self.assertEqual(count, 161)

    def test_retrieve_article_by_code(self):
        url = reverse("api_v1:traffic_law:article-detail", kwargs={"article_code": "art_18"})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["article_code"], "art_18")
        self.assertEqual(response.data["article_label"], "Ingingo ya 18")

    def test_retrieve_bis_article(self):
        url = reverse("api_v1:traffic_law:article-detail", kwargs={"article_code": "art_47_bis"})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["is_bis"])
        self.assertEqual(response.data["article_number"], "47.1")

    def test_filter_articles_by_part(self):
        url = reverse("api_v1:traffic_law:article-list") + "?part=1"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results") if isinstance(response.data, dict) else response.data
        self.assertEqual(len(results), 7)

    def test_list_definitions(self):
        url = reverse("api_v1:traffic_law:definition-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        count = response.data.get("count") if isinstance(response.data, dict) else len(response.data)
        self.assertEqual(count, 43)

    def test_list_signs_and_filter_category(self):
        url = reverse("api_v1:traffic_law:sign-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        count = response.data.get("count") if isinstance(response.data, dict) else len(response.data)
        self.assertEqual(count, 64)

        # Warning signs filter
        warning_url = url + "?category=WARNING"
        warning_resp = self.client.get(warning_url)
        self.assertEqual(warning_resp.status_code, status.HTTP_200_OK)
        warning_count = warning_resp.data.get("count") if isinstance(warning_resp.data, dict) else len(warning_resp.data)
        self.assertEqual(warning_count, 27)

    def test_list_markings(self):
        url = reverse("api_v1:traffic_law:marking-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        count = response.data.get("count") if isinstance(response.data, dict) else len(response.data)
        self.assertEqual(count, 16)

    def test_list_police_evaluations(self):
        url = reverse("api_v1:traffic_law:evaluation-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        count = response.data.get("count") if isinstance(response.data, dict) else len(response.data)
        self.assertEqual(count, 220)

    def test_list_practice_questions(self):
        url = reverse("api_v1:traffic_law:question-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        count = response.data.get("count") if isinstance(response.data, dict) else len(response.data)
        self.assertEqual(count, 401)
