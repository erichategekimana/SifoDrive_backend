from django.db import models
from django.utils.translation import gettext_lazy as _


class NotificationChannel(models.TextChoices):
    SMS = "SMS", _("SMS")
    IN_APP = "IN_APP", _("In-App Notification")
    EMAIL = "EMAIL", _("Email")
    PUSH = "PUSH", _("Push Notification")


class NotificationType(models.TextChoices):
    OTP = "OTP", _("OTP Verification Code")
    WELCOME = "WELCOME", _("Welcome to Sifo Drive")
    GUEST_UPGRADE = "GUEST_UPGRADE", _("Guest Upgraded to Student")
    PAYMENT_SUCCESS = "PAYMENT_SUCCESS", _("Payment Received")
    PAYMENT_FAILED = "PAYMENT_FAILED", _("Payment Failed")
    PAYMENT_REFUNDED = "PAYMENT_REFUNDED", _("Payment Refunded")
    BOOKING_QUEUED = "BOOKING_QUEUED", _("Irembo Slot Queued")
    BOOKING_CONFIRMED = "BOOKING_CONFIRMED", _("Irembo Slot Confirmed")
    BOOKING_SLOTS_EXHAUSTED = "BOOKING_SLOTS_EXHAUSTED", _("Irembo Slots Exhausted")
    BOOKING_REMINDER = "BOOKING_REMINDER", _("Physical Exam Reminder")
    EXAM_RESULT = "EXAM_RESULT", _("Practice Exam Result")
    LIVE_CLASS_SCHEDULED = "LIVE_CLASS_SCHEDULED", _("Live Class Scheduled")
    LIVE_CLASS_REMINDER = "LIVE_CLASS_REMINDER", _("Live Class Starting Soon")
    COURSE_PROGRESS = "COURSE_PROGRESS", _("Course Milestone Reached")
    SECURITY_ALERT = "SECURITY_ALERT", _("Security Alert")
    SYSTEM_ANNOUNCEMENT = "SYSTEM_ANNOUNCEMENT", _("System Announcement")
    GENERAL = "GENERAL", _("General Notification")


class NotificationPriority(models.TextChoices):
    LOW = "LOW", _("Low")
    NORMAL = "NORMAL", _("Normal")
    HIGH = "HIGH", _("High")
    URGENT = "URGENT", _("Urgent")


class NotificationStatus(models.TextChoices):
    PENDING = "PENDING", _("Pending")
    QUEUED = "QUEUED", _("Queued in Worker")
    SENT = "SENT", _("Sent")
    DELIVERED = "DELIVERED", _("Delivered")
    READ = "READ", _("Read")
    FAILED = "FAILED", _("Failed")
    CANCELLED = "CANCELLED", _("Cancelled")
