import uuid
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.lms.models import Course, CourseGroup, CourseGroupMessage, Curriculum

User = get_user_model()


class CourseGroupChatTests(APITestCase):
    def setUp(self):
        self.tutor = User.objects.create_user(
            phone_number="+250788111222",
            email="tutor@sifogroup.com",
            password="testpassword123",
            first_name="Jean",
            last_name="Tutor",
            role="TUTOR",
        )
        self.student = User.objects.create_user(
            phone_number="+250788333444",
            email="student@sifogroup.com",
            password="testpassword123",
            first_name="Alice",
            last_name="Student",
            role="STUDENT",
            student_id="SF-2026-0001",
        )
        self.curriculum = Curriculum.objects.create(
            title="Driver Theory",
            code=f"CURR-{uuid.uuid4().hex[:6]}",
            created_by=self.tutor,
        )
        self.course = Course.objects.create(
            curriculum=self.curriculum,
            title="General Road Rules",
            code=f"CRS-{uuid.uuid4().hex[:6]}",
            created_by=self.tutor,
        )

    def test_course_roster(self):
        self.client.force_authenticate(user=self.student)
        url = f"/api/v1/lms/courses/{self.course.id}/roster/"
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.data["data"]
        self.assertTrue(len(data) >= 2)
        roles = [u["role"] for u in data]
        self.assertIn("Instructor", roles)
        self.assertIn("Student", roles)

    def test_course_groups_list_and_create(self):
        self.client.force_authenticate(user=self.student)
        url = f"/api/v1/lms/courses/{self.course.id}/groups/"

        # List (triggers auto-seed if none)
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(len(res.data["data"]) >= 1)

        # Create new group
        payload = {
            "name": "Weekend Prep Circle",
            "description": "Mock test revisions",
            "category": "Intersections",
        }
        res_create = self.client.post(url, payload, format="json")
        self.assertEqual(res_create.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res_create.data["data"]["name"], "Weekend Prep Circle")
        group_id = res_create.data["data"]["id"]

        # Detail
        detail_url = f"/api/v1/lms/groups/{group_id}/"
        res_detail = self.client.get(detail_url)
        self.assertEqual(res_detail.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_detail.data["data"]["messages"]), 1)

        # Send Message
        msg_url = f"/api/v1/lms/groups/{group_id}/messages/"
        res_msg = self.client.post(msg_url, {"content": "Hello classmates!"}, format="json")
        self.assertEqual(res_msg.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res_msg.data["data"]["text"], "Hello classmates!")

        # Toggle Join
        join_url = f"/api/v1/lms/groups/{group_id}/toggle-join/"
        res_join = self.client.post(join_url)
        self.assertEqual(res_join.status_code, status.HTTP_200_OK)
        self.assertFalse(res_join.data["data"]["is_member"])
