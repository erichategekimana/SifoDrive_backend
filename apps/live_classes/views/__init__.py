"""
apps/live_classes/views/__init__.py
===================================
Facade exposing all live_classes views.
"""

from apps.live_classes.views.attendance_views import (
    ClassAttendanceBatchView,
    ClassAttendanceListView,
    MyAttendanceSummaryView,
    StudentAttendanceDetailView,
)
from apps.live_classes.views.class_views import (
    LiveClassCancelView,
    LiveClassDetailView,
    LiveClassEndView,
    LiveClassListCreateView,
    LiveClassRecurringScheduleView,
    LiveClassRescheduleView,
    LiveClassStartView,
)
from apps.live_classes.views.cohort_views import (
    CohortAssignStudentsView,
    CohortAssignTutorsView,
    CohortDetailView,
    CohortListCreateView,
    CohortSetStatusView,
)
from apps.live_classes.views.resource_views import (
    ClassResourceDetailView,
    ClassResourceListCreateView,
)

__all__ = [
    "CohortListCreateView",
    "CohortDetailView",
    "CohortSetStatusView",
    "CohortAssignStudentsView",
    "CohortAssignTutorsView",
    "LiveClassListCreateView",
    "LiveClassRecurringScheduleView",
    "LiveClassDetailView",
    "LiveClassRescheduleView",
    "LiveClassStartView",
    "LiveClassEndView",
    "LiveClassCancelView",
    "ClassResourceListCreateView",
    "ClassResourceDetailView",
    "ClassAttendanceListView",
    "ClassAttendanceBatchView",
    "MyAttendanceSummaryView",
    "StudentAttendanceDetailView",
]
