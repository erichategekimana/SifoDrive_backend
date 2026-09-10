"""
apps/notifications/tests/test_notifications.py
==============================================
Unit and integration tests for the Sifo Drive notifications system.
"""

from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.constants import UserRole
from apps.notifications.models import (
    Notification,
    NotificationChannel,
    NotificationPreference,
    NotificationPriority,
    NotificationStatus,
    NotificationTemplate,
    NotificationType,
    SMSNotification,
)
from apps.notifications.providers.base import SMSDeliveryResult
from apps.notifications.providers.console import ConsoleSMSProvider
from apps.notifications.providers.factory import get_sms_provider
from apps.notifications.services import (
    NotificationService,
    SMSDispatcherService,
    TemplateService,
)


class TemplateServiceTests(TestCase):
    def test_default_template_fallback_rwanda(self):
        title, body = TemplateService.render(
            notification_type=NotificationType.OTP,
            channel=NotificationChannel.SMS,
            language="rw",
            context={"purpose_label": "Kwemeza konti", "otp_code": "123456", "expiry_minutes": 10},
        )
        self.assertIn("123456", body)
        self.assertIn("10", body)
        self.assertIn("Sifo Drive", body)

    def test_default_template_fallback_english(self):
        title, body = TemplateService.render(
            notification_type=NotificationType.OTP,
            channel=NotificationChannel.SMS,
            language="en",
            context={"purpose_label": "Verify account", "otp_code": "654321", "expiry_minutes": 5},
        )
        self.assertIn("654321", body)
        self.assertIn("5 minutes", body)
        self.assertIn("Verification Code", title)

    def test_db_template_override(self):
        NotificationTemplate.objects.create(
            template_code="CUSTOM_OTP",
            notification_type=NotificationType.OTP,
            channel=NotificationChannel.SMS,
            language="rw",
            title_template="Muraho",
            body_template="Iyi ni kode nshya: {otp_code}",
        )
        title, body = TemplateService.render(
            notification_type=NotificationType.OTP,
            channel=NotificationChannel.SMS,
            language="rw",
            context={"otp_code": "999888"},
            template_code="CUSTOM_OTP",
        )
        self.assertEqual(title, "Muraho")
        self.assertEqual(body, "Iyi ni kode nshya: 999888")

    def test_missing_variables_do_not_crash(self):
        # Safe dict should retain placeholder without KeyError
        title, body = TemplateService.render(
            notification_type=NotificationType.PAYMENT_SUCCESS,
            channel=NotificationChannel.SMS,
            language="en",
            context={},  # No amount_rwf or transaction_ref provided
        )
        self.assertIn("{amount_rwf}", body)


class SMSDispatcherServiceTests(TestCase):
    def test_send_sms_success_with_console_provider(self):
        result = SMSDispatcherService.send_sms(
            phone_number="0781234567",
            message="Test Sifo Drive SMS message",
            message_type=NotificationType.GENERAL,
            provider_name="console",
        )
        self.assertTrue(result.success)
        self.assertEqual(result.status, "SENT")

        # Verify audit log was created in SMSNotification
        sms_log = SMSNotification.objects.filter(recipient_phone="+250781234567").first()
        self.assertIsNotNone(sms_log)
        self.assertEqual(sms_log.status, "SENT")
        self.assertEqual(sms_log.provider, "CONSOLE_MOCK")
        self.assertIn("Test Sifo Drive", sms_log.message_body)

    def test_invalid_phone_number_fails_gracefully(self):
        result = SMSDispatcherService.send_sms(
            phone_number="invalid-phone",
            message="This should not send",
        )
        self.assertFalse(result.success)
        self.assertEqual(result.status, "FAILED")
        self.assertIn("Invalid phone number", result.error_message)


class NotificationServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            phone_number="+250788112233",
            password="StrongPassword123!",
            first_name="Jean",
            last_name="Mugisha",
            role=UserRole.STUDENT,
        )

    def test_send_in_app_notification(self):
        notif = NotificationService.send_notification(
            recipient=self.user,
            notification_type=NotificationType.WELCOME,
            channel=NotificationChannel.IN_APP,
            context={"name": "Jean"},
            action_url="/dashboard",
        )
        self.assertEqual(notif.recipient, self.user)
        self.assertEqual(notif.status, NotificationStatus.DELIVERED)
        self.assertFalse(notif.is_read)
        self.assertEqual(NotificationService.get_unread_count(self.user), 1)

    def test_mark_as_read(self):
        notif = NotificationService.send_welcome(self.user)
        self.assertEqual(NotificationService.get_unread_count(self.user), 1)

        success = NotificationService.mark_as_read(self.user, str(notif.id))
        self.assertTrue(success)
        self.assertEqual(NotificationService.get_unread_count(self.user), 0)

        notif.refresh_from_db()
        self.assertTrue(notif.is_read)
        self.assertIsNotNone(notif.read_at)

    def test_mark_all_as_read(self):
        NotificationService.send_welcome(self.user)
        NotificationService.send_notification(
            recipient=self.user,
            notification_type=NotificationType.COURSE_PROGRESS,
            channel=NotificationChannel.IN_APP,
        )
        self.assertEqual(NotificationService.get_unread_count(self.user), 2)

        count = NotificationService.mark_all_as_read(self.user)
        self.assertEqual(count, 2)
        self.assertEqual(NotificationService.get_unread_count(self.user), 0)

    def test_notification_preference_management(self):
        prefs = NotificationService.get_user_preferences(self.user)
        self.assertTrue(prefs.sms_enabled)
        self.assertEqual(prefs.preferred_language, "rw")

        updated = NotificationService.update_user_preferences(
            self.user,
            sms_enabled=False,
            preferred_language="en",
        )
        self.assertFalse(updated.sms_enabled)
        self.assertEqual(updated.preferred_language, "en")


class NotificationAPITests(TestCase):
    def setUp(self):
        from rest_framework.test import APIClient
        self.client = APIClient()

        self.student = User.objects.create_user(
            phone_number="+250788990011",
            password="StrongPassword123!",
            first_name="Aline",
            last_name="Uwase",
            role=UserRole.STUDENT,
        )
        self.admin = User.objects.create_user(
            phone_number="+250788000000",
            password="AdminPassword123!",
            first_name="Admin",
            last_name="System",
            role=UserRole.SYSTEM_ADMIN,
        )

    def test_user_inbox_and_unread_count_api(self):
        self.client.force_authenticate(user=self.student)

        # Initially 0 unread
        res = self.client.get("/api/v1/notifications/unread-count/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["data"]["unread_count"], 0)

        # Create two notifications
        notif1 = NotificationService.send_welcome(self.student)
        notif2 = NotificationService.send_notification(
            recipient=self.student,
            notification_type=NotificationType.COURSE_PROGRESS,
            channel=NotificationChannel.IN_APP,
        )

        # Unread count is now 2
        res = self.client.get("/api/v1/notifications/unread-count/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["data"]["unread_count"], 2)

        # List notifications
        res = self.client.get("/api/v1/notifications/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data["results"]), 2)

        # Mark first notification as read
        res = self.client.post(f"/api/v1/notifications/{notif1.id}/read/")
        self.assertEqual(res.status_code, 200)

        # Unread count is now 1
        res = self.client.get("/api/v1/notifications/unread-count/")
        self.assertEqual(res.data["data"]["unread_count"], 1)

        # Mark all as read
        res = self.client.post("/api/v1/notifications/read-all/")
        self.assertEqual(res.status_code, 200)

        res = self.client.get("/api/v1/notifications/unread-count/")
        self.assertEqual(res.data["data"]["unread_count"], 0)

    def test_user_preferences_api(self):
        self.client.force_authenticate(user=self.student)

        # GET preferences
        res = self.client.get("/api/v1/notifications/preferences/")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data["data"]["sms_enabled"])

        # PUT update preferences
        res = self.client.put(
            "/api/v1/notifications/preferences/",
            data={"sms_enabled": False, "preferred_language": "en"},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.data["data"]["sms_enabled"])
        self.assertEqual(res.data["data"]["preferred_language"], "en")

    def test_admin_sms_logs_restricted(self):
        # Student should be forbidden from accessing admin SMS logs
        self.client.force_authenticate(user=self.student)
        res = self.client.get("/api/v1/notifications/admin/sms-logs/")
        self.assertEqual(res.status_code, 403)

        # System Admin is allowed
        self.client.force_authenticate(user=self.admin)
        res = self.client.get("/api/v1/notifications/admin/sms-logs/")
        self.assertEqual(res.status_code, 200)

