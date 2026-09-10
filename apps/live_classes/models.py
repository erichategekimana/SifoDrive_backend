"""
apps/live_classes/models.py
============================
Live class scheduling and attendance models.
"""
from django.db import models
from django.utils.translation import gettext_lazy as _
from apps.core.models import BaseModel


class LiveClass(BaseModel):
    """A scheduled Google Meet live tutoring session."""
    title = models.CharField(_('Title'), max_length=200)
    topic = models.CharField(_('Topic'), max_length=300, blank=True)
    tutor = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, related_name='tutored_classes')
    license_category = models.CharField(_('License Category'), max_length=5, blank=True)
    scheduled_date = models.DateField(_('Date'), db_index=True)
    start_time = models.TimeField(_('Start Time'))
    end_time = models.TimeField(_('End Time'))
    google_meet_url = models.URLField(_('Google Meet URL'))
    is_published = models.BooleanField(_('Published'), default=False)
    notes = models.TextField(_('Session Notes'), blank=True)
    recording_url = models.URLField(_('Recording URL'), blank=True)

    class Meta(BaseModel.Meta):
        verbose_name = _('Live Class')
        ordering = ['scheduled_date', 'start_time']

    def __str__(self):
        return f'{self.title} — {self.scheduled_date}'


class ClassAttendance(BaseModel):
    """Records when a student joined a live class (feeds exam eligibility engine)."""
    STATUSES = [
        ('JOINED_LIVE_CLASS', 'Joined Live'),
        ('WATCHED_RECORDING', 'Watched Recording'),
    ]
    student = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='class_attendances')
    live_class = models.ForeignKey(LiveClass, on_delete=models.CASCADE, related_name='attendances')
    status = models.CharField(_('Status'), max_length=25, choices=STATUSES)
    joined_at = models.DateTimeField(_('Joined At'), auto_now_add=True)

    class Meta(BaseModel.Meta):
        verbose_name = _('Class Attendance')
        unique_together = [['student', 'live_class']]

    def __str__(self):
        return f'{self.student.phone_number} — {self.live_class.title}'
