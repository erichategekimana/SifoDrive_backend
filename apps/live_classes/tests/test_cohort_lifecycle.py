"""
apps/live_classes/tests/test_cohort_lifecycle.py
================================================
Comprehensive tests for Cohort status transitions:
- Default status is 'queue'
- Admin can open a cohort (making it default)
- Only ONE cohort can be 'open' at a time (previous open cohort auto-closes)
- Cannot open expired or full cohorts
- Auto-close when capacity is reached
- Auto-end when end date passes
- Auto-enrollment of new registering students, admin-created students, and upgraded guests into the open cohort
- Permission enforcement on set-status endpoint
"""

from datetime import date, timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.constants import AccountStatus, UserRole
from apps.accounts.serializers import AdminCreateUserSerializer, StudentRegistrationSerializer
from apps.accounts.services import StudentService
from apps.live_classes.models import Cohort
from apps.live_classes.models.cohort import CohortStatus
from apps.live_classes.services import CohortService

User = get_user_model()


class CohortLifecycleTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.system_admin = User.objects.create_user(
            phone_number="+250788000001",
            password="SecurePassword123!",
            role=UserRole.SYSTEM_ADMIN,
            status=AccountStatus.ACTIVE,
            first_name="Sys",
            last_name="Admin",
            terms_of_service_accepted=True,
            privacy_policy_accepted=True,
        )

        self.training_admin = User.objects.create_user(
            phone_number="+250788000002",
            password="SecurePassword123!",
            role=UserRole.TRAINING_ADMIN,
            status=AccountStatus.ACTIVE,
            first_name="Training",
            last_name="Admin",
            terms_of_service_accepted=True,
            privacy_policy_accepted=True,
        )

        self.student = User.objects.create_user(
            phone_number="+250788000003",
            password="SecurePassword123!",
            role=UserRole.STUDENT,
            status=AccountStatus.ACTIVE,
            first_name="Alice",
            last_name="Student",
            terms_of_service_accepted=True,
            privacy_policy_accepted=True,
        )

    def test_cohort_default_status_is_queue(self):
        today = timezone.now().date()
        cohort = CohortService.create_cohort(
            name="Batch Alpha",
            code="BATCH-ALPHA",
            start_date=today,
            end_date=today + timedelta(days=30),
            max_capacity=20,
        )
        self.assertEqual(cohort.status, CohortStatus.QUEUE)

    def test_admin_set_cohort_open(self):
        today = timezone.now().date()
        cohort = CohortService.create_cohort(
            name="Batch Beta",
            code="BATCH-BETA",
            start_date=today,
            end_date=today + timedelta(days=30),
            max_capacity=25,
        )
        self.assertEqual(cohort.status, CohortStatus.QUEUE)

        # Set open via service
        CohortService.set_cohort_open(cohort)
        cohort.refresh_from_db()
        self.assertEqual(cohort.status, CohortStatus.OPEN)

        # It is returned as default open cohort
        default_cohort = CohortService.get_default_open_cohort()
        self.assertIsNotNone(default_cohort)
        self.assertEqual(default_cohort.id, cohort.id)

    def test_single_open_cohort_enforcement(self):
        today = timezone.now().date()
        cohort1 = CohortService.create_cohort(
            name="Batch 1",
            code="BATCH-1",
            start_date=today,
            end_date=today + timedelta(days=30),
        )
        cohort2 = CohortService.create_cohort(
            name="Batch 2",
            code="BATCH-2",
            start_date=today,
            end_date=today + timedelta(days=30),
        )

        # Open cohort 1
        CohortService.set_cohort_open(cohort1)
        cohort1.refresh_from_db()
        self.assertEqual(cohort1.status, CohortStatus.OPEN)

        # Open cohort 2 -> cohort 1 must automatically change to closed
        CohortService.set_cohort_open(cohort2)
        cohort1.refresh_from_db()
        cohort2.refresh_from_db()

        self.assertEqual(cohort1.status, CohortStatus.CLOSED)
        self.assertEqual(cohort2.status, CohortStatus.OPEN)

        default_cohort = CohortService.get_default_open_cohort()
        self.assertEqual(default_cohort.id, cohort2.id)

    def test_cannot_open_past_cohort(self):
        today = timezone.now().date()
        cohort = Cohort.objects.create(
            name="Past Batch",
            code="PAST-BATCH",
            start_date=today - timedelta(days=60),
            end_date=today - timedelta(days=10),
            max_capacity=10,
            status=CohortStatus.QUEUE,
        )
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            CohortService.set_cohort_open(cohort)

    def test_cannot_open_full_cohort(self):
        today = timezone.now().date()
        cohort = Cohort.objects.create(
            name="Full Batch",
            code="FULL-BATCH",
            start_date=today,
            end_date=today + timedelta(days=30),
            max_capacity=1,
            status=CohortStatus.QUEUE,
        )
        cohort.students.add(self.student)

        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            CohortService.set_cohort_open(cohort)

    def test_auto_close_on_capacity_reached(self):
        today = timezone.now().date()
        cohort = CohortService.create_cohort(
            name="Capacity Batch",
            code="CAP-BATCH",
            start_date=today,
            end_date=today + timedelta(days=30),
            max_capacity=2,
        )
        CohortService.set_cohort_open(cohort)
        cohort.refresh_from_db()
        self.assertEqual(cohort.status, CohortStatus.OPEN)

        student2 = User.objects.create_user(
            phone_number="+250788000004",
            password="SecurePassword123!",
            role=UserRole.STUDENT,
            status=AccountStatus.ACTIVE,
            first_name="Bob",
            last_name="Student",
        )

        # Enroll first student -> still open (1/2)
        CohortService.enroll_students(cohort, [self.student.id])
        cohort.refresh_from_db()
        self.assertEqual(cohort.status, CohortStatus.OPEN)

        # Enroll second student -> reaches capacity (2/2) -> auto-closes
        CohortService.enroll_students(cohort, [student2.id])
        cohort.refresh_from_db()
        self.assertEqual(cohort.status, CohortStatus.CLOSED)

    def test_auto_end_on_end_date_reached(self):
        today = timezone.now().date()
        cohort = Cohort.objects.create(
            name="Ending Batch",
            code="END-BATCH",
            start_date=today - timedelta(days=30),
            end_date=today - timedelta(days=1),
            max_capacity=20,
            status=CohortStatus.OPEN,
        )
        cohort.evaluate_status(save=True)
        cohort.refresh_from_db()
        self.assertEqual(cohort.status, CohortStatus.ENDED)

    def test_auto_enroll_new_registered_student_in_open_cohort(self):
        today = timezone.now().date()
        open_cohort = CohortService.create_cohort(
            name="Current Intake",
            code="INTAKE-2026-OCT",
            start_date=today,
            end_date=today + timedelta(days=60),
            max_capacity=50,
        )
        CohortService.set_cohort_open(open_cohort)

        # Register a new student via StudentRegistrationSerializer
        data = {
            "first_name": "New",
            "last_name": "Learner",
            "phone_number": "+250788999888",
            "email": "learner@example.rw",
            "password": "SecurePassword123!",
            "terms_of_service_accepted": True,
            "privacy_policy_accepted": True,
        }
        serializer = StudentRegistrationSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        new_user = serializer.save()

        # Should be auto-enrolled in open_cohort
        open_cohort.refresh_from_db()
        self.assertTrue(open_cohort.students.filter(pk=new_user.pk).exists())
        self.assertEqual(new_user.enrolled_cohorts.first().id, open_cohort.id)

    def test_auto_enroll_admin_created_student_in_open_cohort(self):
        today = timezone.now().date()
        open_cohort = CohortService.create_cohort(
            name="Admin Intake",
            code="INTAKE-ADMIN",
            start_date=today,
            end_date=today + timedelta(days=60),
            max_capacity=50,
        )
        CohortService.set_cohort_open(open_cohort)

        admin_data = {
            "first_name": "Created",
            "last_name": "ByAdmin",
            "phone_number": "+250788111222",
            "email": "created@example.rw",
            "password": "SecurePassword123!",
            "role": UserRole.STUDENT,
        }
        serializer = AdminCreateUserSerializer(data=admin_data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        created_user = serializer.save()

        open_cohort.refresh_from_db()
        self.assertTrue(open_cohort.students.filter(pk=created_user.pk).exists())

    def test_auto_enroll_upgraded_guest_in_open_cohort(self):
        today = timezone.now().date()
        open_cohort = CohortService.create_cohort(
            name="Upgrade Intake",
            code="INTAKE-UPGRADE",
            start_date=today,
            end_date=today + timedelta(days=60),
            max_capacity=50,
        )
        CohortService.set_cohort_open(open_cohort)

        guest = User.objects.create_user(
            phone_number="+250788444555",
            password="SecurePassword123!",
            role=UserRole.GUEST,
            status=AccountStatus.ACTIVE,
            first_name="Guest",
            last_name="User",
            privacy_policy_accepted=True,
        )
        StudentService.upgrade_guest_to_student(guest)

        open_cohort.refresh_from_db()
        self.assertTrue(open_cohort.students.filter(pk=guest.pk).exists())

    def test_cohort_set_status_endpoint(self):
        today = timezone.now().date()
        cohort = CohortService.create_cohort(
            name="Endpoint Cohort",
            code="ENDPOINT-COHORT",
            start_date=today,
            end_date=today + timedelta(days=30),
            max_capacity=20,
        )

        url = reverse("api_v1:live_classes:cohort-set-status", kwargs={"pk": cohort.pk})

        # Student cannot change status
        self.client.force_authenticate(user=self.student)
        res = self.client.post(url, {"status": "open"})
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # Training admin can change status to open
        self.client.force_authenticate(user=self.training_admin)
        res = self.client.post(url, {"status": "open"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        cohort.refresh_from_db()
        self.assertEqual(cohort.status, CohortStatus.OPEN)

        # Training admin can close it
        res = self.client.post(url, {"status": "closed"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        cohort.refresh_from_db()
        self.assertEqual(cohort.status, CohortStatus.CLOSED)

    def test_cohort_identifier_and_default_capacity_60(self):
        """
        Requirements:
        - Cohort capacity is 60 students by default.
        - Cohorts can have the same name, but have a 3-digit auto-generated identifier (001, 002, ...).
        """
        today = timezone.now().date()
        # Create first cohort
        c1 = CohortService.create_cohort(
            name="Morning Cohort",
            start_date=today,
            end_date=today + timedelta(days=30),
        )
        self.assertEqual(c1.max_capacity, 60)
        self.assertIsNotNone(c1.identifier)
        self.assertEqual(len(c1.identifier), 3)

        # Create second cohort with the same name
        c2 = CohortService.create_cohort(
            name="Morning Cohort",
            start_date=today,
            end_date=today + timedelta(days=30),
        )
        self.assertEqual(c2.max_capacity, 60)
        self.assertEqual(c2.name, c1.name)
        self.assertNotEqual(c2.identifier, c1.identifier)
        self.assertEqual(int(c2.identifier), int(c1.identifier) + 1)

    def test_cohort_identifier_role_visibility(self):
        """
        Requirements:
        - Identifier is visible to training admin, system admin, and board reviewer.
        - Identifier is NOT visible to student, tutor, or guest.
        """
        from apps.live_classes.serializers import CohortListSerializer
        from rest_framework.test import APIRequestFactory

        today = timezone.now().date()
        cohort = CohortService.create_cohort(
            name="Visibility Test Cohort",
            start_date=today,
            end_date=today + timedelta(days=30),
        )

        board_reviewer = User.objects.create_user(
            phone_number="+250788000004",
            password="SecurePassword123!",
            role=UserRole.BOARD_REVIEWER,
            status=AccountStatus.ACTIVE,
            first_name="Board",
            last_name="Reviewer",
        )
        tutor = User.objects.create_user(
            phone_number="+250788000005",
            password="SecurePassword123!",
            role=UserRole.TUTOR,
            status=AccountStatus.ACTIVE,
            first_name="Test",
            last_name="Tutor",
        )

        factory = APIRequestFactory()

        # System Admin
        req_sys = factory.get("/")
        req_sys.user = self.system_admin
        data_sys = CohortListSerializer(cohort, context={"request": req_sys}).data
        self.assertEqual(data_sys.get("identifier"), cohort.identifier)

        # Training Admin
        req_tr = factory.get("/")
        req_tr.user = self.training_admin
        data_tr = CohortListSerializer(cohort, context={"request": req_tr}).data
        self.assertEqual(data_tr.get("identifier"), cohort.identifier)

        # Board Reviewer
        req_br = factory.get("/")
        req_br.user = board_reviewer
        data_br = CohortListSerializer(cohort, context={"request": req_br}).data
        self.assertEqual(data_br.get("identifier"), cohort.identifier)

        # Student (should be None)
        req_stu = factory.get("/")
        req_stu.user = self.student
        data_stu = CohortListSerializer(cohort, context={"request": req_stu}).data
        self.assertIsNone(data_stu.get("identifier"))

        # Tutor (should be None)
        req_tut = factory.get("/")
        req_tut.user = tutor
        data_tut = CohortListSerializer(cohort, context={"request": req_tut}).data
        self.assertIsNone(data_tut.get("identifier"))

    def test_student_registration_without_open_cohort_defers_student_id(self):
        """
        Requirements:
        - If student registers but there's no open cohort, he'll wait until training admin or
          system admin assigns him to a cohort.
        - That's when ID will be generated and it will be used to track him from then on.
        - Student ID format: starts with 'SDS' followed by 11 more chars (cohort id 3 + year 4 + seq 4).
        """
        # Ensure no open cohorts exist
        Cohort.objects.filter(status=CohortStatus.OPEN).update(status=CohortStatus.CLOSED)

        reg_data = {
            "first_name": "Waiting",
            "last_name": "Student",
            "phone_number": "+250788999888",
            "email": "waiting@example.rw",
            "password": "SecurePassword123!",
            "terms_of_service_accepted": True,
            "privacy_policy_accepted": True,
        }
        serializer = StudentRegistrationSerializer(data=reg_data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        student = serializer.save()

        # Verify student_id is None because no open cohort was available
        self.assertIsNone(student.student_id)

        # Now admin creates a cohort
        today = timezone.now().date()
        cohort = CohortService.create_cohort(
            name="Assigned Cohort",
            start_date=today,
            end_date=today + timedelta(days=60),
            max_capacity=60,
        )

        # Admin assigns student to this cohort
        CohortService.enroll_students(cohort, [student])
        student.refresh_from_db()

        # Now student_id is generated
        self.assertIsNotNone(student.student_id)
        # Format: SDS + 11 chars (3 cohort id + 4 year + 4 seq) = 14 chars
        self.assertTrue(student.student_id.startswith("SDS"))
        self.assertEqual(len(student.student_id), 14)
        expected_cohort_id = cohort.identifier
        self.assertEqual(student.student_id[3:6], expected_cohort_id)
        year_str = str(timezone.now().year)
        self.assertEqual(student.student_id[6:10], year_str)
        self.assertEqual(student.student_id[10:], "0001")

    def test_student_registration_with_open_cohort_generates_student_id_immediately(self):
        """
        When open cohort exists, registration immediately enrolls student and generates
        the cohort-formatted student ID.
        """
        today = timezone.now().date()
        open_cohort = CohortService.create_cohort(
            name="Immediate Open Cohort",
            start_date=today,
            end_date=today + timedelta(days=60),
            max_capacity=60,
        )
        CohortService.set_cohort_open(open_cohort)

        reg_data = {
            "first_name": "Immediate",
            "last_name": "Student",
            "phone_number": "+250788999777",
            "email": "immediate@example.rw",
            "password": "SecurePassword123!",
            "terms_of_service_accepted": True,
            "privacy_policy_accepted": True,
        }
        serializer = StudentRegistrationSerializer(data=reg_data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        student = serializer.save()

        student.refresh_from_db()
        self.assertIsNotNone(student.student_id)
        self.assertTrue(student.student_id.startswith("SDS"))
        self.assertEqual(len(student.student_id), 14)
        self.assertEqual(student.student_id[3:6], open_cohort.identifier)
        self.assertTrue(open_cohort.students.filter(pk=student.pk).exists())
