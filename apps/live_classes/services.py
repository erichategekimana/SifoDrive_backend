"""apps/live_classes/services.py
Attendance tracking and eligibility calculations."""
import logging
logger = logging.getLogger(__name__)

class AttendanceService:
    @classmethod
    def get_attendance_rate(cls, user) -> float:
        """Return attendance rate 0.0–1.0 for a student."""
        # TODO: implement
        return 0.0
