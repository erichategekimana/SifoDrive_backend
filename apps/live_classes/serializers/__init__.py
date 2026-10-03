"""
apps/live_classes/serializers/__init__.py
=========================================
Facade exposing all live_classes serializers.
"""

from apps.live_classes.serializers.cohort_serializers import (
    CohortAssignStudentsSerializer,
    CohortAssignTutorsSerializer,
    CohortCreateUpdateSerializer,
    CohortDetailSerializer,
    CohortListSerializer,
    CohortSetStatusSerializer,
    UserBriefSerializer,
)
from apps.live_classes.serializers.resource_serializers import (
    ClassResourceCreateSerializer,
    ClassResourceSerializer,
)
from apps.live_classes.serializers.class_serializers import (
    LiveClassCreateUpdateSerializer,
    LiveClassDetailSerializer,
    LiveClassEndSessionSerializer,
    LiveClassListSerializer,
    LiveClassRecurringScheduleSerializer,
    LiveClassRescheduleSerializer,
)
from apps.live_classes.serializers.attendance_serializers import (
    BatchAttendanceItemSerializer,
    BatchAttendanceRecordSerializer,
    ClassAttendanceSerializer,
    StudentAttendanceSummarySerializer,
)

__all__ = [
    "UserBriefSerializer",
    "CohortListSerializer",
    "CohortDetailSerializer",
    "CohortCreateUpdateSerializer",
    "CohortSetStatusSerializer",
    "CohortAssignStudentsSerializer",
    "CohortAssignTutorsSerializer",
    "ClassResourceSerializer",
    "ClassResourceCreateSerializer",
    "LiveClassListSerializer",
    "LiveClassDetailSerializer",
    "LiveClassCreateUpdateSerializer",
    "LiveClassRescheduleSerializer",
    "LiveClassEndSessionSerializer",
    "LiveClassRecurringScheduleSerializer",
    "ClassAttendanceSerializer",
    "BatchAttendanceItemSerializer",
    "BatchAttendanceRecordSerializer",
    "StudentAttendanceSummarySerializer",
]
