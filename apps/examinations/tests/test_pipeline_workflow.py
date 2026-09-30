from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.constants import UserRole
from apps.accounts.models import User
from apps.examinations.models import ExamSession, ExamSessionStatus


class ExaminationPipelineWorkflowTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Users for each role
        self.student = User.objects.create_user(
            phone_number="+250788111222",
            password="StrongPassword123!",
            first_name="Jean",
            last_name="Paul",
            role=UserRole.STUDENT,
        )
        self.board_reviewer = User.objects.create_user(
            phone_number="+250788333444",
            password="StrongPassword123!",
            first_name="Officer",
            last_name="Reviewer",
            role=UserRole.BOARD_REVIEWER,
        )
        self.training_admin = User.objects.create_user(
            phone_number="+250788555666",
            password="StrongPassword123!",
            first_name="Training",
            last_name="Director",
            role=UserRole.TRAINING_ADMIN,
        )
        self.system_admin = User.objects.create_user(
            phone_number="+250788777888",
            password="StrongPassword123!",
            first_name="System",
            last_name="SuperAdmin",
            role=UserRole.SYSTEM_ADMIN,
        )

        # Submitted exam session awaiting Stage 1 Board Review
        self.session = ExamSession.objects.create(
            student=self.student,
            track="B2C",
            status=ExamSessionStatus.BOARD_REVIEW,
            score=18,
            total_questions=20,
            passed=True,
        )

    def test_stage_1_board_review_enforcement(self):
        """
        Stage 1: Only Board Reviewer can approve or reject.
        Comment is mandatory to approve.
        Other roles have read-only access.
        """
        url = f"/api/v1/examinations/admin/sessions/{self.session.id}/action/"

        # 1. Training Admin attempts Board Review -> Denied
        self.client.force_authenticate(user=self.training_admin)
        res = self.client.post(url, {"action": "BOARD_DECISION", "decision": "APPROVE", "notes": "Premature"})
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # 2. System Admin attempts Board Review -> Denied (System Admin cannot bypass Board Review)
        self.client.force_authenticate(user=self.system_admin)
        res = self.client.post(url, {"action": "BOARD_DECISION", "decision": "APPROVE", "notes": "Bypassing"})
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # 3. Board Reviewer approves WITHOUT comment -> Fails validation
        self.client.force_authenticate(user=self.board_reviewer)
        res = self.client.post(url, {"action": "BOARD_DECISION", "decision": "APPROVE", "notes": ""})
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data.get("error", {}).get("code"), "COMMENT_REQUIRED")

        # 4. Board Reviewer approves WITH comment -> Success, moves to TRAINING_REVIEW
        res = self.client.post(url, {"action": "BOARD_DECISION", "decision": "APPROVE", "notes": "Verified answers and law compliance."})
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        self.session.refresh_from_db()
        self.assertEqual(self.session.status, ExamSessionStatus.TRAINING_REVIEW)
        self.assertEqual(self.session.board_reviewer, self.board_reviewer)
        self.assertEqual(self.session.board_notes, "Verified answers and law compliance.")

        # 5. Board Reviewer attempts to modify again -> Locked (no way back)
        res = self.client.post(url, {"action": "BOARD_DECISION", "decision": "REJECT", "notes": "Too late"})
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data.get("error", {}).get("code"), "GOVERNANCE_LOCK")

    def test_stage_2_training_admin_audit_enforcement(self):
        """
        Stage 2: Only Training Admin can audit and approve.
        Comment is mandatory.
        Board Reviewer and System Admin have read-only access.
        """
        # Advance session to Stage 2
        self.session.status = ExamSessionStatus.TRAINING_REVIEW
        self.session.board_reviewer = self.board_reviewer
        self.session.board_decision = "APPROVE"
        self.session.board_notes = "Board approved"
        self.session.save()

        url = f"/api/v1/examinations/admin/sessions/{self.session.id}/action/"

        # 1. Board Reviewer attempts Stage 2 -> Denied
        self.client.force_authenticate(user=self.board_reviewer)
        res = self.client.post(url, {"action": "TRAINING_DECISION", "decision": "APPROVE", "notes": "Not allowed"})
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # 2. System Admin attempts Stage 2 -> Denied
        self.client.force_authenticate(user=self.system_admin)
        res = self.client.post(url, {"action": "TRAINING_DECISION", "decision": "APPROVE", "notes": "Bypassing audit"})
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # 3. Training Admin approves WITHOUT comment -> Fails validation
        self.client.force_authenticate(user=self.training_admin)
        res = self.client.post(url, {"action": "TRAINING_DECISION", "decision": "APPROVE", "notes": ""})
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data.get("error", {}).get("code"), "COMMENT_REQUIRED")

        # 4. Training Admin approves WITH comment -> Success, moves to SYSTEM_REVIEW
        res = self.client.post(url, {"action": "TRAINING_DECISION", "decision": "APPROVE", "notes": "Pedagogical integrity validated."})
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        self.session.refresh_from_db()
        self.assertEqual(self.session.status, ExamSessionStatus.SYSTEM_REVIEW)
        self.assertEqual(self.session.training_admin, self.training_admin)
        self.assertEqual(self.session.training_notes, "Pedagogical integrity validated.")

        # 5. Training Admin attempts to modify again -> Locked (no way back)
        res = self.client.post(url, {"action": "TRAINING_DECISION", "decision": "REJECT", "notes": "Too late"})
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data.get("error", {}).get("code"), "GOVERNANCE_LOCK")

    def test_stage_3_system_admin_approval_and_publish(self):
        """
        Stage 3: Only System Admin can approve & auto-generate certificate, then publish.
        Board Reviewer and Training Admin have read-only access.
        """
        # Advance session to Stage 3
        self.session.status = ExamSessionStatus.SYSTEM_REVIEW
        self.session.board_reviewer = self.board_reviewer
        self.session.board_decision = "APPROVE"
        self.session.training_admin = self.training_admin
        self.session.training_decision = "APPROVE"
        self.session.save()

        url = f"/api/v1/examinations/admin/sessions/{self.session.id}/action/"

        # 1. Board Reviewer attempts Stage 3 -> Denied
        self.client.force_authenticate(user=self.board_reviewer)
        res = self.client.post(url, {"action": "SYSTEM_APPROVE", "decision": "APPROVE"})
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # 2. Training Admin attempts Stage 3 -> Denied
        self.client.force_authenticate(user=self.training_admin)
        res = self.client.post(url, {"action": "SYSTEM_APPROVE", "decision": "APPROVE"})
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # 3. System Admin approves -> Success, certificate auto-generated
        self.client.force_authenticate(user=self.system_admin)
        res = self.client.post(url, {"action": "SYSTEM_APPROVE", "decision": "APPROVE", "notes": "Official certification granted."})
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        self.session.refresh_from_db()
        self.assertEqual(self.session.status, ExamSessionStatus.APPROVED)
        self.assertEqual(self.session.approved_by, self.system_admin)
        self.assertIsNotNone(self.session.certificate)

        # 4. System Admin publishes exam to candidate portal
        publish_url = "/api/v1/examinations/admin/sessions/publish/"
        pub_res = self.client.post(publish_url, {"publish_type": "SINGLE", "session_id": str(self.session.id)})
        self.assertEqual(pub_res.status_code, status.HTTP_200_OK)

        self.session.refresh_from_db()
        self.assertEqual(self.session.status, ExamSessionStatus.PUBLISHED)
        self.assertTrue(self.session.is_published)
        self.assertEqual(self.session.published_by, self.system_admin)
