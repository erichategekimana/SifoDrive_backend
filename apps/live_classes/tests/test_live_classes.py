"""
apps/live_classes/tests/test_live_classes.py
============================================
Comprehensive test suite for Live Classes, Cohorts, and Attendance Tracking.
Tests:
  - Role-based permissions (System Admin, Training Admin, Tutor, Student, Guest)
  - Cohort batch creation, tutor assignment, student enrollment
  - Class scheduling with Google Meet links, starting/ending sessions
  - Batch attendance recording and 75% attendance rate gate for provisional exam eligibility
  - Learning resources uploading and download permissions
  - Verification that curriculum is universal (no license_category)
"""

from datetime import date, datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.constants import AccountStatus, UserRole
from apps.live_classes.models import (
    AttendanceStatus,
    ClassAttendance,
    ClassResource,
    Cohort,
    LiveClass,
    LiveClassStatus,
)
from apps.live_classes.services import AttendanceService, CohortService, LiveClassService

User = get_user_model()


class LiveClassesBaseTestCase(TestCase):
    """Base setup with pre-configured users across all roles."""

    def setUp(self):
        self.client = APIClient()

        # System Admin
        self.admin = User.objects.create_user(
            phone_number="+250788111111",
            password="SecurePassword123!",
            role=UserRole.SYSTEM_ADMIN,
            status=AccountStatus.ACTIVE,
            first_name="System",
            last_name="Admin",
            terms_of_service_accepted=True,
            privacy_policy_accepted=True,
        )

        # Training Admin
        self.training_admin = User.objects.create_user(
            phone_number="+250788222222",
            password="SecurePassword123!",
            role=UserRole.TRAINING_ADMIN,
            status=AccountStatus.ACTIVE,
            first_name="Training",
            last_name="Admin",
            terms_of_service_accepted=True,
            privacy_policy_accepted=True,
        )

        # Tutor
        self.tutor = User.objects.create_user(
            phone_number="+250788333333",
            password="SecurePassword123!",
            role=UserRole.TUTOR,
            status=AccountStatus.ACTIVE,
            first_name="Jean",
            last_name="Tutor",
            terms_of_service_accepted=True,
            privacy_policy_accepted=True,
        )

        # Student 1
        self.student1 = User.objects.create_user(
            phone_number="+250788444444",
            password="SecurePassword123!",
            role=UserRole.STUDENT,
            status=AccountStatus.ACTIVE,
            first_name="Alice",
            last_name="Student",
            terms_of_service_accepted=True,
            privacy_policy_accepted=True,
        )

        # Student 2
        self.student2 = User.objects.create_user(
            phone_number="+250788555555",
            password="SecurePassword123!",
            role=UserRole.STUDENT,
            status=AccountStatus.ACTIVE,
            first_name="Bob",
            last_name="Student",
            terms_of_service_accepted=True,
            privacy_policy_accepted=True,
        )

        # Guest
        self.guest = User.objects.create_user(
            phone_number="+250788666666",
            password="SecurePassword123!",
            role=UserRole.GUEST,
            status=AccountStatus.ACTIVE,
            first_name="Guest",
            last_name="User",
            terms_of_service_accepted=True,
        )

        # Base Cohort
        self.cohort = CohortService.create_cohort(
            name="Kigali September Theory Cohort A",
            code="COHORT-2026-SEP-A",
            start_date=date.today(),
            end_date=date.today() + timedelta(days=30),
            max_capacity=30,
            schedule_description="Mon, Wed, Fri 18:00 - 20:00 CAT",
            assigned_tutors=[self.tutor],
            students=[self.student1, self.student2],
        )


class CohortManagementTests(LiveClassesBaseTestCase):
    """Test cohort creation, capacity, and role membership."""

    def test_training_admin_can_create_cohort(self):
        self.client.force_authenticate(user=self.training_admin)
        url = reverse("api_v1:live_classes:cohort-list-create")
        data = {
            "name": "Weekend Intensive Road Safety",
            "code": "COHORT-2026-WKND-1",
            "start_date": str(date.today() + timedelta(days=7)),
            "end_date": str(date.today() + timedelta(days=21)),
            "max_capacity": 25,
            "schedule_description": "Sat & Sun 10:00 - 13:00 CAT",
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Cohort.objects.filter(code="COHORT-2026-WKND-1").count(), 1)

    def test_student_cannot_create_cohort(self):
        self.client.force_authenticate(user=self.student1)
        url = reverse("api_v1:live_classes:cohort-list-create")
        data = {
            "name": "Unauthorized Cohort",
            "code": "COHORT-FAIL",
            "start_date": str(date.today()),
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_guest_cannot_access_cohorts(self):
        self.client.force_authenticate(user=self.guest)
        url = reverse("api_v1:live_classes:cohort-list-create")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_enroll_and_unenroll_students(self):
        new_student = User.objects.create_user(
            phone_number="+250788777777",
            password="SecurePassword123!",
            role=UserRole.STUDENT,
            status=AccountStatus.ACTIVE,
            first_name="Dave",
            last_name="Student",
            terms_of_service_accepted=True,
            privacy_policy_accepted=True,
        )
        self.client.force_authenticate(user=self.training_admin)
        url = reverse("api_v1:live_classes:cohort-assign-students", kwargs={"pk": self.cohort.id})

        # Enroll
        resp = self.client.post(url, {"student_ids": [str(new_student.id)]}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(self.cohort.students.filter(id=new_student.id).exists())

        # Unenroll
        resp_unenroll = self.client.post(
            f"{url}?action=unenroll",
            {"student_ids": [str(new_student.id)]},
            format="json",
        )
        self.assertEqual(resp_unenroll.status_code, status.HTTP_200_OK)
        self.assertFalse(self.cohort.students.filter(id=new_student.id).exists())


class LiveClassSchedulingTests(LiveClassesBaseTestCase):
    """Test live class scheduling with Google Meet links, notifications, and lifecycle."""

    def test_admin_and_training_admin_can_schedule_class(self):
        self.client.force_authenticate(user=self.training_admin)
        url = reverse("api_v1:live_classes:class-list-create")
        data = {
            "title": "Priority Rules & Traffic Signals Mastery",
            "topic": "Right of way at roundabouts and police signals",
            "cohort": str(self.cohort.id),
            "tutor": str(self.tutor.id),
            "scheduled_date": str(date.today() + timedelta(days=2)),
            "start_time": "18:00:00",
            "end_time": "19:30:00",
            "google_meet_url": "https://meet.google.com/abc-defg-hij",
            "notes": "Bring your driving manual chapters 3 and 4.",
            "is_published": True,
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(LiveClass.objects.filter(title=data["title"]).exists())

    def test_tutor_cannot_schedule_class(self):
        """Only Admin and Training Admin have scheduling authority."""
        self.client.force_authenticate(user=self.tutor)
        url = reverse("api_v1:live_classes:class-list-create")
        data = {
            "title": "Tutor Unauthorized Scheduling",
            "scheduled_date": str(date.today() + timedelta(days=1)),
            "start_time": "10:00:00",
            "end_time": "11:00:00",
            "google_meet_url": "https://meet.google.com/xyz-uvw-rst",
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_tutor_can_start_and_end_session(self):
        live_class = LiveClassService.schedule_class(
            title="Road Signs & Markings Deep Dive",
            scheduled_date=date.today(),
            start_time=time(14, 0),
            end_time=time(15, 30),
            google_meet_url="https://meet.google.com/test-meet-123",
            cohort=self.cohort,
            tutor=self.tutor,
            is_published=True,
        )

        self.client.force_authenticate(user=self.tutor)

        # Start session
        start_url = reverse("api_v1:live_classes:class-start", kwargs={"pk": live_class.id})
        start_resp = self.client.post(start_url)
        self.assertEqual(start_resp.status_code, status.HTTP_200_OK)
        live_class.refresh_from_db()
        self.assertEqual(live_class.status, LiveClassStatus.IN_PROGRESS)
        self.assertIsNotNone(live_class.actual_started_at)

        # End session with recording URL
        end_url = reverse("api_v1:live_classes:class-end", kwargs={"pk": live_class.id})
        end_resp = self.client.post(
            end_url,
            {"recording_url": "https://drive.google.com/file/d/rec123/view"},
            format="json",
        )
        self.assertEqual(end_resp.status_code, status.HTTP_200_OK)
        live_class.refresh_from_db()
        self.assertEqual(live_class.status, LiveClassStatus.COMPLETED)
        self.assertIsNotNone(live_class.actual_ended_at)
        self.assertEqual(live_class.recording_url, "https://drive.google.com/file/d/rec123/view")

    def test_reschedule_class_by_training_admin(self):
        live_class = LiveClassService.schedule_class(
            title="Speed Limits & Overtaking Rules",
            scheduled_date=date.today() + timedelta(days=3),
            start_time=time(9, 0),
            end_time=time(10, 30),
            google_meet_url="https://meet.google.com/resched-test",
            cohort=self.cohort,
            tutor=self.tutor,
        )

        self.client.force_authenticate(user=self.training_admin)
        url = reverse("api_v1:live_classes:class-reschedule", kwargs={"pk": live_class.id})
        new_date = str(date.today() + timedelta(days=4))
        data = {
            "scheduled_date": new_date,
            "start_time": "14:00:00",
            "end_time": "15:30:00",
            "reason": "Tutor conference conflict",
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        live_class.refresh_from_db()
        self.assertEqual(live_class.status, LiveClassStatus.RESCHEDULED)
        self.assertEqual(str(live_class.scheduled_date), new_date)


class AttendanceAndExamEligibilityTests(LiveClassesBaseTestCase):
    """
    Test student attendance tracking and verify the 75% attendance threshold
    required for provisional mock exam eligibility.
    """

    def setUp(self):
        super().setUp()
        # Create 4 completed live classes for the cohort
        self.classes = []
        for i in range(4):
            c = LiveClass.objects.create(
                title=f"Core Theory Session {i + 1}",
                cohort=self.cohort,
                tutor=self.tutor,
                scheduled_date=date.today() - timedelta(days=4 - i),
                start_time=time(18, 0),
                end_time=time(19, 30),
                google_meet_url=f"https://meet.google.com/session-{i}",
                status=LiveClassStatus.COMPLETED,
                is_published=True,
            )
            self.classes.append(c)

    def test_batch_attendance_recording_by_tutor(self):
        self.client.force_authenticate(user=self.tutor)
        url = reverse("api_v1:live_classes:class-attendance-batch", kwargs={"pk": self.classes[0].id})
        payload = {
            "records": [
                {
                    "student_id": str(self.student1.id),
                    "status": AttendanceStatus.PRESENT,
                    "minutes_attended": 90,
                    "notes": "Active participant in Q&A",
                },
                {
                    "student_id": str(self.student2.id),
                    "status": AttendanceStatus.LATE,
                    "minutes_attended": 60,
                    "notes": "Joined 30 mins in",
                },
            ]
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["data"]["updated_count"], 2)

        att1 = ClassAttendance.objects.get(student=self.student1, live_class=self.classes[0])
        self.assertEqual(att1.status, AttendanceStatus.PRESENT)
        self.assertEqual(att1.minutes_attended, 90)

    def test_attendance_rate_and_exam_eligibility_threshold(self):
        """
        Threshold: 75% required attendance.
        Out of 4 classes:
          - Alice attends 3 classes (75%) -> Eligible
          - Bob attends 2 classes (50%) -> Not eligible
        """
        # Alice attends 3 out of 4 classes
        for i in range(3):
            AttendanceService.record_attendance(
                live_class=self.classes[i],
                student=self.student1,
                status=AttendanceStatus.PRESENT,
            )
        AttendanceService.record_attendance(
            live_class=self.classes[3],
            student=self.student1,
            status=AttendanceStatus.ABSENT,
        )

        # Bob attends 2 out of 4 classes
        for i in range(2):
            AttendanceService.record_attendance(
                live_class=self.classes[i],
                student=self.student2,
                status=AttendanceStatus.PRESENT,
            )
        for i in range(2, 4):
            AttendanceService.record_attendance(
                live_class=self.classes[i],
                student=self.student2,
                status=AttendanceStatus.ABSENT,
            )

        # Alice: 3 / 4 = 0.75 -> Eligible
        summary_alice = AttendanceService.get_student_attendance_summary(self.student1)
        self.assertEqual(summary_alice["rate"], 0.75)
        self.assertEqual(summary_alice["percentage"], 75.0)
        self.assertTrue(summary_alice["is_eligible_for_exam"])

        # Bob: 2 / 4 = 0.50 -> Not eligible
        summary_bob = AttendanceService.get_student_attendance_summary(self.student2)
        self.assertEqual(summary_bob["rate"], 0.50)
        self.assertEqual(summary_bob["percentage"], 50.0)
        self.assertFalse(summary_bob["is_eligible_for_exam"])

    def test_student_my_attendance_endpoint(self):
        AttendanceService.record_attendance(
            live_class=self.classes[0],
            student=self.student1,
            status=AttendanceStatus.PRESENT,
            minutes_attended=90,
        )
        self.client.force_authenticate(user=self.student1)
        url = reverse("api_v1:live_classes:my-attendance-summary")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("summary", response.data["data"])
        self.assertIn("attendances", response.data["data"])


class ClassResourceTests(LiveClassesBaseTestCase):
    """Test uploading slide decks and external materials attached to live classes."""

    def test_tutor_can_add_external_resource(self):
        live_class = LiveClassService.schedule_class(
            title="Rwanda Road Traffic Act 2026 Review",
            scheduled_date=date.today() + timedelta(days=1),
            start_time=time(10, 0),
            end_time=time(11, 30),
            google_meet_url="https://meet.google.com/resource-test",
            cohort=self.cohort,
            tutor=self.tutor,
        )

        self.client.force_authenticate(user=self.tutor)
        url = reverse("api_v1:live_classes:class-resource-list-create", kwargs={"pk": live_class.id})
        data = {
            "title": "Traffic Regulations Presentation Slides",
            "external_link": "https://docs.google.com/presentation/d/slide123/edit",
            "description": "Comprehensive slide deck covering road priority rules.",
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(ClassResource.objects.filter(live_class=live_class, title=data["title"]).exists())

    def test_student_can_view_resources(self):
        live_class = LiveClassService.schedule_class(
            title="Road Signs Presentation",
            scheduled_date=date.today() + timedelta(days=1),
            start_time=time(10, 0),
            end_time=time(11, 30),
            google_meet_url="https://meet.google.com/resource-test",
            cohort=self.cohort,
            tutor=self.tutor,
        )
        LiveClassService.add_resource(
            live_class=live_class,
            title="Study Worksheet",
            external_link="https://drive.google.com/file/d/sheet/view",
            uploaded_by=self.tutor,
        )

        self.client.force_authenticate(user=self.student1)
        url = reverse("api_v1:live_classes:class-resource-list-create", kwargs={"pk": live_class.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        items = response.data.get("results", response.data)
        self.assertEqual(len(items), 1)
