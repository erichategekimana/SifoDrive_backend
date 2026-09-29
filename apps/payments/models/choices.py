"""
apps/payments/models/choices.py
===============================
Payment providers, fee types, and transaction status constants.
"""

PROVIDERS = [
    ('MTN', 'MTN Mobile Money'),
    ('AIRTEL', 'Airtel Money'),
]

FEE_TYPES = [
    ('STUDENT_TUITION', 'Student Tuition Fee'),
    ('GUEST_EXAM_PASS', 'Guest Exam Single Pass'),
    ('ENTERPRISE_LICENSE', 'Enterprise Lab License'),
    ('IREMBO_CONCIERGE', 'Irembo Concierge Fee'),
]

STATUSES = [
    ('INITIATED', 'Initiated'),
    ('PENDING', 'Pending MoMo Approval'),
    ('SUCCESSFUL', 'Successful'),
    ('FAILED', 'Failed'),
    ('REFUNDED', 'Refunded'),
]
