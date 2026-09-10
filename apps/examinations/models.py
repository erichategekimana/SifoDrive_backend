"""
apps/examinations/models.py
============================
Exam engine models: ExamSession, SessionQuestion, ProctoringEvent, ExamResult.
"""
from django.db import models
from django.utils.translation import gettext_lazy as _
from apps.core.models import BaseModel


class ExamSession(BaseModel):
    """A single exam attempt by a student or guest."""
    TRACKS = [('B2C', 'Personal (Remote)'), ('B2B', 'Enterprise Lab')]
    STATUSES = [
        ('PENDING', 'Pending Pre-flight'),
        ('ACTIVE', 'In Progress'),
        ('SUBMITTED', 'Submitted — Awaiting Review'),
        ('GRADED', 'Graded — Board Certified'),
        ('FLAGGED', 'Flagged — Integrity Violation'),
        ('EXPIRED', 'Expired — Time Limit Exceeded'),
    ]
    student = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='exam_sessions')
    track = models.CharField(_('Track'), max_length=5, choices=TRACKS, default='B2C')
    status = models.CharField(_('Status'), max_length=20, choices=STATUSES, default='PENDING', db_index=True)
    started_at = models.DateTimeField(_('Started At'), null=True, blank=True)
    submitted_at = models.DateTimeField(_('Submitted At'), null=True, blank=True)
    expires_at = models.DateTimeField(_('Expires At'), null=True, blank=True)
    score = models.PositiveSmallIntegerField(_('Score'), null=True, blank=True)
    total_questions = models.PositiveSmallIntegerField(_('Total Questions'), default=20)
    passed = models.BooleanField(_('Passed'), null=True, blank=True)
    device_fingerprint = models.CharField(_('Device Fingerprint'), max_length=200, blank=True)
    violation_count = models.PositiveSmallIntegerField(_('Violation Count'), default=0)

    class Meta(BaseModel.Meta):
        verbose_name = _('Exam Session')

    def __str__(self):
        return f'Exam [{self.track}] — {self.student.phone_number} — {self.status}'

    @property
    def passing_score(self) -> int:
        return 12  # 60% of 20 questions

    @property
    def is_passed(self) -> bool:
        return self.score is not None and self.score >= self.passing_score


class SessionQuestion(BaseModel):
    """One question as it appears in an exam session (immutable snapshot)."""
    session = models.ForeignKey(ExamSession, on_delete=models.CASCADE, related_name='session_questions')
    question = models.ForeignKey('lms.QuizQuestion', on_delete=models.PROTECT, related_name='session_appearances')
    selected_option = models.CharField(_('Selected Option'), max_length=1, blank=True, default='')
    is_correct = models.BooleanField(_('Correct'), null=True, blank=True)
    answered_at = models.DateTimeField(_('Answered At'), null=True, blank=True)
    sequence_number = models.PositiveSmallIntegerField(_('Sequence'), default=0)

    class Meta(BaseModel.Meta):
        ordering = ['sequence_number']
        unique_together = [['session', 'sequence_number']]


class ProctoringEvent(BaseModel):
    """Records a proctoring event (snapshot, violation, blur, etc.) during B2C exams."""
    EVENT_TYPES = [
        ('SNAPSHOT', 'Scheduled Webcam Snapshot'),
        ('ANOMALY_SNAPSHOT', 'Anomaly-Triggered Snapshot'),
        ('WINDOW_BLUR', 'Window Lost Focus'),
        ('TAB_SWITCH', 'Tab Switch Detected'),
        ('FULLSCREEN_EXIT', 'Fullscreen Exited'),
        ('MOBILE_BLOCKED', 'Mobile Device Blocked'),
        ('SESSION_START', 'Session Started'),
        ('SESSION_END', 'Session Ended'),
    ]
    session = models.ForeignKey(ExamSession, on_delete=models.CASCADE, related_name='proctoring_events')
    event_type = models.CharField(_('Event Type'), max_length=30, choices=EVENT_TYPES, db_index=True)
    snapshot_image = models.ImageField(_('Snapshot'), upload_to='proctoring/snapshots/%Y/%m/', null=True, blank=True)
    metadata = models.JSONField(_('Metadata'), default=dict, blank=True)
    is_violation = models.BooleanField(_('Is Violation'), default=False, db_index=True)

    class Meta(BaseModel.Meta):
        verbose_name = _('Proctoring Event')
        ordering = ['created_at']
