"""
apps/booking/urls.py
====================
URL routes for Driving Test Booking applications, category fees,
partner teachers, and administrative slot booking workflow.
"""

from django.urls import path

from apps.booking.views import (
    AdminBookingAssignAgentView,
    AdminBookingCompleteView,
    AdminBookingOrderDetailView,
    AdminBookingOrderListView,
    AdminBookingStatusUpdateView,
    AdminCategoryPriceDetailView,
    AdminCategoryPriceListCreateView,
    AdminPartnerTeacherDetailView,
    AdminPartnerTeacherListCreateView,
    BookingApplicationCreateView,
    BookingCancelView,
    BookingDetailView,
    CategoryPricingListView,
    DistrictsMetadataView,
    MyBookingsListView,
    PartnerTeacherDropdownListView,
)

app_name = "booking"

urlpatterns = [
    # ── Public & Metadata ───────────────────────────────────────────────────
    path("pricing/", CategoryPricingListView.as_view(), name="pricing"),
    path("districts/", DistrictsMetadataView.as_view(), name="districts"),
    path("teachers/", PartnerTeacherDropdownListView.as_view(), name="teachers"),

    # ── User Applications ───────────────────────────────────────────────────
    path("apply/", BookingApplicationCreateView.as_view(), name="apply"),
    path("my-bookings/", MyBookingsListView.as_view(), name="my_bookings"),
    path("<uuid:pk>/", BookingDetailView.as_view(), name="detail"),
    path("<uuid:pk>/cancel/", BookingCancelView.as_view(), name="cancel"),

    # ── Admin Operations & Agent Queue ──────────────────────────────────────
    path("admin/orders/", AdminBookingOrderListView.as_view(), name="admin_orders"),
    path("admin/orders/<uuid:pk>/", AdminBookingOrderDetailView.as_view(), name="admin_order_detail"),
    path("admin/orders/<uuid:pk>/assign/", AdminBookingAssignAgentView.as_view(), name="admin_assign_agent"),
    path("admin/orders/<uuid:pk>/status/", AdminBookingStatusUpdateView.as_view(), name="admin_status_update"),
    path("admin/orders/<uuid:pk>/complete/", AdminBookingCompleteView.as_view(), name="admin_complete"),

    # ── Admin Partner Teachers & Pricing CRUD ───────────────────────────────
    path("admin/teachers/", AdminPartnerTeacherListCreateView.as_view(), name="admin_teachers"),
    path("admin/teachers/<uuid:pk>/", AdminPartnerTeacherDetailView.as_view(), name="admin_teacher_detail"),
    path("admin/pricing/", AdminCategoryPriceListCreateView.as_view(), name="admin_pricing"),
    path("admin/pricing/<uuid:pk>/", AdminCategoryPriceDetailView.as_view(), name="admin_pricing_detail"),
]
