"""
apps/booking/tests/test_booking.py
==================================
Unit and API integration tests for the Driving Test Booking Concierge.
Tests district validation, Kicukiro sites, partner teachers, pricing schedules,
and Irembo slot completion workflow with billing numbers.
"""

from datetime import date
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework.exceptions import ValidationError

from apps.accounts.constants import UserRole
from apps.accounts.models import User
from apps.booking.models import (
    BookingApplication,
    BookingState,
    CategoryPrice,
    KicukiroWorkingSite,
    LicenseCategory,
    PartnerTeacher,
    RwandaDistrict,
)
from apps.booking.services import BookingService, CategoryPriceService, PartnerTeacherService
from apps.core.exceptions import PermissionDeniedException


class BookingModelAndServiceTests(TestCase):
    def setUp(self):
        self.applicant = User.objects.create_user(
            phone_number="+250788123456",
            password="StrongPassword123!",
            first_name="Eric",
            last_name="Mugisha",
            role=UserRole.STUDENT,
        )
        self.agent = User.objects.create_user(
            phone_number="+250788999888",
            password="AgentPassword123!",
            first_name="Agent",
            last_name="Booking",
            role=UserRole.SYSTEM_ADMIN,
        )
        # Configure category prices
        CategoryPriceService.set_price(
            category=LicenseCategory.B,
            price_rwf=12000,
            description="Category B Light Vehicle Test",
        )
        CategoryPriceService.set_price(
            category=LicenseCategory.A,
            price_rwf=6000,
            description="Category A Motorcycle Test",
        )
        # Create partner teacher
        self.teacher = PartnerTeacherService.create_teacher(
            first_name="Claude",
            last_name="Habimana",
            phone_number="+250783111222",
            driving_school_affiliation="Inyange Driving Academy",
        )

    def test_pricing_schedule_lookup(self):
        # Custom set price
        self.assertEqual(CategoryPrice.get_price_for_category(LicenseCategory.B), 12000)
        self.assertEqual(CategoryPrice.get_price_for_category(LicenseCategory.A), 6000)
        # Fallback price for unconfigured category C
        self.assertEqual(CategoryPrice.get_price_for_category(LicenseCategory.C), 15000)

    def test_apply_booking_success_standard_district(self):
        booking = BookingService.apply_for_booking(
            applicant=self.applicant,
            first_name="Eric",
            last_name="Mugisha",
            phone_number="+250788123456",
            national_id="1199580012345678",
            date_of_birth=date(1995, 5, 20),
            license_category=LicenseCategory.B,
            preferred_district=RwandaDistrict.GASABO,
            working_site=None,
            partner_teacher_id=str(self.teacher.id),
        )

        self.assertIsNotNone(booking.id)
        self.assertTrue(booking.ticket_number.startswith("BK-"))
        self.assertEqual(booking.state, BookingState.PENDING)
        self.assertEqual(booking.price_rwf, 12000)
        self.assertEqual(booking.partner_teacher, self.teacher)
        self.assertIsNone(booking.working_site)

        # Test PII encryption
        self.assertNotEqual(booking.national_id_encrypted, "1199580012345678")
        decrypted_nid = booking.get_decrypted_national_id()
        self.assertEqual(decrypted_nid, "1199580012345678")

    def test_apply_booking_kicukiro_requires_working_site(self):
        # Missing site for Kicukiro must raise ValidationError
        with self.assertRaises(ValidationError) as ctx:
            BookingService.apply_for_booking(
                applicant=self.applicant,
                first_name="Eric",
                last_name="Mugisha",
                phone_number="+250788123456",
                national_id="1199580012345678",
                date_of_birth=date(1995, 5, 20),
                license_category=LicenseCategory.B,
                preferred_district=RwandaDistrict.KICUKIRO,
                working_site=None,
            )
        self.assertIn("working_site", str(ctx.exception))

    def test_apply_booking_kicukiro_valid_sites(self):
        # 1. BUSANZA AUTOMATED CENTER
        booking1 = BookingService.apply_for_booking(
            applicant=self.applicant,
            first_name="Eric",
            last_name="Mugisha",
            phone_number="+250788123456",
            national_id="1199580012345678",
            date_of_birth=date(1995, 5, 20),
            license_category=LicenseCategory.B,
            preferred_district=RwandaDistrict.KICUKIRO,
            working_site=KicukiroWorkingSite.BUSANZA_AUTOMATED,
        )
        self.assertEqual(booking1.working_site, KicukiroWorkingSite.BUSANZA_AUTOMATED)

        # 2. BUSANZA SITE (KIC)
        booking2 = BookingService.apply_for_booking(
            applicant=self.applicant,
            first_name="Eric",
            last_name="Mugisha",
            phone_number="+250788123456",
            national_id="1199580012345678",
            date_of_birth=date(1995, 5, 20),
            license_category=LicenseCategory.A,
            preferred_district=RwandaDistrict.KICUKIRO,
            working_site=KicukiroWorkingSite.BUSANZA_SITE_KIC,
        )
        self.assertEqual(booking2.working_site, KicukiroWorkingSite.BUSANZA_SITE_KIC)

    def test_apply_booking_underage_rejected(self):
        today = date.today()
        underage_dob = date(today.year - 17, today.month, today.day)
        with self.assertRaises(ValidationError) as ctx:
            BookingService.apply_for_booking(
                applicant=self.applicant,
                first_name="Junior",
                last_name="Underage",
                phone_number="+250788123456",
                national_id="1200780012345678",
                date_of_birth=underage_dob,
                license_category=LicenseCategory.B,
                preferred_district=RwandaDistrict.GASABO,
            )
        self.assertIn("18 years", str(ctx.exception))

    def test_regular_student_without_partner_teacher(self):
        # Dropdown can be left to None for regular students
        booking = BookingService.apply_for_booking(
            applicant=self.applicant,
            first_name="Eric",
            last_name="Mugisha",
            phone_number="+250788123456",
            national_id="1199580012345678",
            date_of_birth=date(1995, 5, 20),
            license_category=LicenseCategory.B,
            preferred_district=RwandaDistrict.GASABO,
            partner_teacher_id=None,
        )
        self.assertIsNone(booking.partner_teacher)

    def test_admin_workflow_complete_with_billing_number(self):
        booking = BookingService.apply_for_booking(
            applicant=self.applicant,
            first_name="Eric",
            last_name="Mugisha",
            phone_number="+250788123456",
            national_id="1199580012345678",
            date_of_birth=date(1995, 5, 20),
            license_category=LicenseCategory.B,
            preferred_district=RwandaDistrict.KICUKIRO,
            working_site=KicukiroWorkingSite.BUSANZA_AUTOMATED,
        )

        # 1. Assign agent
        BookingService.assign_agent(booking_id=str(booking.id), agent=self.agent)
        booking.refresh_from_db()
        self.assertEqual(booking.state, BookingState.PROCESSING)
        self.assertEqual(booking.assigned_agent, self.agent)

        # 2. Agent completes booking and attaches Irembo billing number
        completed = BookingService.complete_booking(
            booking_id=str(booking.id),
            agent=self.agent,
            irembo_billing_number="IRMB-2026-990088",
            test_date="2026-10-15",
            venue="Busanza Automated Testing Center",
            agent_notes="Slot successfully booked on Irembo. Applicant notified.",
        )
        self.assertEqual(completed.state, BookingState.COMPLETED)
        self.assertEqual(completed.irembo_billing_number, "IRMB-2026-990088")
        self.assertEqual(str(completed.confirmed_test_date), "2026-10-15")
        self.assertEqual(completed.confirmed_venue, "Busanza Automated Testing Center")
        self.assertIsNotNone(completed.completed_at)


class BookingAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.student = User.objects.create_user(
            phone_number="+250788111222",
            password="Password123!",
            first_name="Sonia",
            last_name="Uwamahoro",
            role=UserRole.STUDENT,
        )
        self.admin = User.objects.create_user(
            phone_number="+250788000999",
            password="AdminPassword123!",
            first_name="Admin",
            last_name="Officer",
            role=UserRole.SYSTEM_ADMIN,
        )
        self.teacher = PartnerTeacherService.create_teacher(
            first_name="Jean",
            last_name="Kamanzi",
            phone_number="+250788777666",
            driving_school_affiliation="Kigali Driving Experts",
        )
        CategoryPriceService.set_price(
            category=LicenseCategory.B,
            price_rwf=10000,
        )

    def test_public_pricing_endpoint(self):
        res = self.client.get("/api/v1/booking/pricing/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("pricing_schedule", res.data["data"])
        schedule = res.data["data"]["pricing_schedule"]
        cat_b = next(item for item in schedule if item["category"] == "B")
        self.assertEqual(cat_b["price_rwf"], 10000)

    def test_public_districts_metadata_endpoint(self):
        res = self.client.get("/api/v1/booking/districts/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("districts", res.data["data"])
        self.assertIn("kicukiro_working_sites", res.data["data"])
        kic_rule = res.data["data"]["special_district_rules"]["KICUKIRO"]
        self.assertTrue(kic_rule["requires_working_site"])

    def test_teachers_dropdown_endpoint(self):
        self.client.force_authenticate(user=self.student)
        res = self.client.get("/api/v1/booking/teachers/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data["data"]), 1)
        self.assertEqual(res.data["data"][0]["full_name"], "Jean Kamanzi")

    def test_apply_booking_api(self):
        self.client.force_authenticate(user=self.student)
        payload = {
            "first_name": "Sonia",
            "last_name": "Uwamahoro",
            "phone_number": "+250788111222",
            "national_id": "1199880012345678",
            "date_of_birth": "1998-04-12",
            "license_category": "B",
            "preferred_district": "KICUKIRO",
            "working_site": "BUSANZA AUTOMATED CENTER",
            "partner_teacher_id": str(self.teacher.id),
        }
        res = self.client.post("/api/v1/booking/apply/", data=payload, format="json")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["data"]["license_category"], "B")
        self.assertEqual(res.data["data"]["working_site"], "BUSANZA AUTOMATED CENTER")
        self.assertEqual(res.data["data"]["state"], "PENDING")

        # List user's bookings
        list_res = self.client.get("/api/v1/booking/my-bookings/")
        self.assertEqual(list_res.status_code, 200)
        self.assertEqual(len(list_res.data["results"]), 1)

    def test_admin_complete_booking_api(self):
        # Create booking as student
        booking = BookingService.apply_for_booking(
            applicant=self.student,
            first_name="Sonia",
            last_name="Uwamahoro",
            phone_number="+250788111222",
            national_id="1199880012345678",
            date_of_birth=date(1998, 4, 12),
            license_category=LicenseCategory.B,
            preferred_district=RwandaDistrict.GASABO,
        )

        # Student cannot complete booking
        self.client.force_authenticate(user=self.student)
        res = self.client.post(
            f"/api/v1/booking/admin/orders/{booking.id}/complete/",
            data={"irembo_billing_number": "IRMB-123456"},
            format="json",
        )
        self.assertEqual(res.status_code, 403)

        # Admin completes booking
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            f"/api/v1/booking/admin/orders/{booking.id}/complete/",
            data={
                "irembo_billing_number": "IRMB-998877",
                "confirmed_test_date": "2026-11-20",
                "confirmed_venue": "Gasabo Testing Site",
            },
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["data"]["state"], "COMPLETED")
        self.assertEqual(res.data["data"]["irembo_billing_number"], "IRMB-998877")
