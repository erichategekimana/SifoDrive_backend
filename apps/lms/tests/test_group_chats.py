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
        # Create an admin user who should NOT appear in the course roster
        admin_user = User.objects.create_user(
            phone_number="+250788999111",
            email="admin@sifogroup.com",
            password="testpassword123",
            first_name="Admin",
            last_name="Super",
            role="SYSTEM_ADMIN",
        )

        self.client.force_authenticate(user=self.student)
        url = f"/api/v1/lms/courses/{self.course.id}/roster/"
        res = self.client.get(url)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.data["data"]
        self.assertTrue(len(data) >= 2)
        roles = [u["role"] for u in data]
        self.assertIn("Instructor", roles)
        self.assertIn("Student", roles)
        user_ids = [str(u["id"]) for u in data]
        self.assertNotIn(str(admin_user.id), user_ids)

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

    def test_student_created_group_allows_any_member_to_add_peers(self):
        # Create 2 other students
        student2 = User.objects.create_user(
            phone_number="+250788555666",
            email="student2@sifogroup.com",
            password="testpassword123",
            first_name="Bob",
            last_name="Learner",
            role="STUDENT",
        )
        student3 = User.objects.create_user(
            phone_number="+250788777888",
            email="student3@sifogroup.com",
            password="testpassword123",
            first_name="Charlie",
            last_name="Cadet",
            role="STUDENT",
        )

        # Student 1 creates group
        self.client.force_authenticate(user=self.student)
        res = self.client.post(
            f"/api/v1/lms/courses/{self.course.id}/groups/",
            {"name": "Student Study Circle", "category": "General"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        group_id = res.data["data"]["id"]

        # Student 2 joins group
        self.client.force_authenticate(user=student2)
        res_join = self.client.post(f"/api/v1/lms/groups/{group_id}/toggle-join/")
        self.assertEqual(res_join.status_code, status.HTTP_200_OK)
        self.assertTrue(res_join.data["data"]["is_member"])

        # Check detail: student2 is a member, and can_add_members must be True because student created the group!
        res_detail = self.client.get(f"/api/v1/lms/groups/{group_id}/")
        self.assertTrue(res_detail.data["data"]["can_add_members"])

        # Student 2 adds Student 3
        res_add = self.client.post(
            f"/api/v1/lms/groups/{group_id}/members/",
            {"user_id": str(student3.id)},
            format="json",
        )
        self.assertEqual(res_add.status_code, status.HTTP_200_OK)
        member_ids = [m["id"] for m in res_add.data["data"]["members"]]
        self.assertIn(str(student3.id), member_ids)

    def test_tutor_group_permissions_and_delegation(self):
        student2 = User.objects.create_user(
            phone_number="+250788999000",
            email="student2_tutor@sifogroup.com",
            password="testpassword123",
            first_name="David",
            last_name="Driver",
            role="STUDENT",
        )

        # 1. Tutor creates group with allow_students_to_add_members=False
        self.client.force_authenticate(user=self.tutor)
        res = self.client.post(
            f"/api/v1/lms/courses/{self.course.id}/groups/",
            {
                "name": "Tutor Masterclass Group",
                "category": "Intersections",
                "allow_students_to_add_members": False,
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        group_id = res.data["data"]["id"]

        # Tutor adds self.student
        res_add = self.client.post(
            f"/api/v1/lms/groups/{group_id}/members/",
            {"user_id": str(self.student.id)},
            format="json",
        )
        self.assertEqual(res_add.status_code, status.HTTP_200_OK)

        # 2. Student is member, but tutor has NOT granted access to add others
        self.client.force_authenticate(user=self.student)
        res_detail = self.client.get(f"/api/v1/lms/groups/{group_id}/")
        self.assertFalse(res_detail.data["data"]["can_add_members"])

        # Student tries to add student2 -> 403 Forbidden
        res_fail = self.client.post(
            f"/api/v1/lms/groups/{group_id}/members/",
            {"user_id": str(student2.id)},
            format="json",
        )
        self.assertEqual(res_fail.status_code, status.HTTP_403_FORBIDDEN)

        # 3. Tutor provides that access to others by updating allow_students_to_add_members=True
        self.client.force_authenticate(user=self.tutor)
        res_patch = self.client.patch(
            f"/api/v1/lms/groups/{group_id}/",
            {"allow_students_to_add_members": True},
            format="json",
        )
        self.assertEqual(res_patch.status_code, status.HTTP_200_OK)
        self.assertTrue(res_patch.data["data"]["allow_students_to_add_members"])

        # 4. Now self.student has access and can add student2!
        self.client.force_authenticate(user=self.student)
        res_detail2 = self.client.get(f"/api/v1/lms/groups/{group_id}/")
        self.assertTrue(res_detail2.data["data"]["can_add_members"])

        res_success = self.client.post(
            f"/api/v1/lms/groups/{group_id}/members/",
            {"user_id": str(student2.id)},
            format="json",
        )
        self.assertEqual(res_success.status_code, status.HTTP_200_OK)
        member_ids = [m["id"] for m in res_success.data["data"]["members"]]
        self.assertIn(str(student2.id), member_ids)
