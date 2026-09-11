"""
apps/live_classes/urls.py
=========================
URL routing configuration for the Live Classes application.
Mounted at /api/v1/live-classes/.
"""

from django.urls import path

from .views import (
    ClassAttendanceBatchView,
    ClassAttendanceListView,
    ClassResourceDetailView,
    ClassResourceListCreateView,
    CohortAssignStudentsView,
    CohortAssignTutorsView,
    CohortDetailView,
    CohortListCreateView,
    LiveClassCancelView,
    LiveClassDetailView,
    LiveClassEndView,
    LiveClassListCreateView,
    LiveClassRescheduleView,
    LiveClassStartView,
    MyAttendanceSummaryView,
    StudentAttendanceDetailView,
)

app_name = "live_classes"

urlpatterns = [
    # Cohorts
    path("cohorts/", CohortListCreateView.as_view(), name="cohort-list-create"),
    path("cohorts/<uuid:pk>/", CohortDetailView.as_view(), name="cohort-detail"),
    path("cohorts/<uuid:pk>/assign-students/", CohortAssignStudentsView.as_view(), name="cohort-assign-students"),
    path("cohorts/<uuid:pk>/assign-tutors/", CohortAssignTutorsView.as_view(), name="cohort-assign-tutors"),

    # Live Classes
    path("", LiveClassListCreateView.as_view(), name="class-list-create-root"),
    path("classes/", LiveClassListCreateView.as_view(), name="class-list-create"),
    path("classes/<uuid:pk>/", LiveClassDetailView.as_view(), name="class-detail"),
    path("classes/<uuid:pk>/reschedule/", LiveClassRescheduleView.as_view(), name="class-reschedule"),
    path("classes/<uuid:pk>/start/", LiveClassStartView.as_view(), name="class-start"),
    path("classes/<uuid:pk>/end/", LiveClassEndView.as_view(), name="class-end"),
    path("classes/<uuid:pk>/cancel/", LiveClassCancelView.as_view(), name="class-cancel"),

    # Class Resources
    path("classes/<uuid:pk>/resources/", ClassResourceListCreateView.as_view(), name="class-resource-list-create"),
    path("resources/<uuid:pk>/", ClassResourceDetailView.as_view(), name="class-resource-detail"),

    # Attendance Tracking
    path("classes/<uuid:pk>/attendance/", ClassAttendanceListView.as_view(), name="class-attendance-list"),
    path("classes/<uuid:pk>/attendance/batch/", ClassAttendanceBatchView.as_view(), name="class-attendance-batch"),
    path("my-attendance/", MyAttendanceSummaryView.as_view(), name="my-attendance-summary"),
    path("students/<uuid:student_id>/attendance/", StudentAttendanceDetailView.as_view(), name="student-attendance-detail"),
]
