from rest_framework import generics
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView

from apps.booking.models import (
    CategoryPrice,
    KicukiroWorkingSite,
    LicenseCategory,
    PartnerTeacher,
    RwandaDistrict,
)
from apps.booking.serializers import (
    CategoryPriceSerializer,
    PartnerTeacherAdminSerializer,
    PartnerTeacherDropdownSerializer,
)
from apps.core.mixins import SuccessResponseMixin
from apps.core.permissions import IsAdminLevel, IsSystemAdmin


class CategoryPricingListView(SuccessResponseMixin, APIView):
    """
    Public endpoint: lists all driving test license categories and their booking service fees.
    """
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        # Fetch configured prices
        prices = CategoryPrice.objects.filter(is_active=True).order_by("category")
        serializer = CategoryPriceSerializer(prices, many=True)

        # Build fallback list for any category not explicitly in database
        configured_cats = {p.category for p in prices}
        all_categories = []
        for cat_choice in LicenseCategory.choices:
            cat_val, cat_label = cat_choice
            price_val = CategoryPrice.get_price_for_category(cat_val)
            all_categories.append({
                "category": cat_val,
                "label": cat_label,
                "price_rwf": price_val,
                "currency": "RWF",
                "is_custom_configured": cat_val in configured_cats,
            })

        return self.success_response(
            data={
                "pricing_schedule": all_categories,
                "configured_records": serializer.data,
            },
            message="Category pricing schedule fetched successfully.",
        )


class DistrictsMetadataView(SuccessResponseMixin, APIView):
    """
    Public endpoint: returns recognized Rwandan districts and Kicukiro working sites.
    """
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        districts = [
            {"code": code, "name": label} for code, label in RwandaDistrict.choices
        ]
        kicukiro_sites = [
            {"code": code, "name": label} for code, label in KicukiroWorkingSite.choices
        ]

        return self.success_response(
            data={
                "districts": districts,
                "kicukiro_working_sites": kicukiro_sites,
                "special_district_rules": {
                    "KICUKIRO": {
                        "requires_working_site": True,
                        "allowed_sites": [s[0] for s in KicukiroWorkingSite.choices],
                    }
                }
            },
            message="Districts and working sites metadata fetched successfully.",
        )


class PartnerTeacherDropdownListView(SuccessResponseMixin, generics.ListAPIView):
    """
    Authenticated endpoint: returns active partner driving teachers for dropdown selection.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = PartnerTeacherDropdownSerializer
    pagination_class = None
    queryset = PartnerTeacher.objects.filter(is_active=True).order_by("first_name", "last_name")

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        return self.success_response(data=serializer.data)


class AdminPartnerTeacherListCreateView(SuccessResponseMixin, generics.ListCreateAPIView):
    """Admin CRUD: list and add partner driving teachers."""
    permission_classes = [IsAuthenticated, IsAdminLevel]
    serializer_class = PartnerTeacherAdminSerializer
    queryset = PartnerTeacher.objects.all().order_by("first_name", "last_name")


class AdminPartnerTeacherDetailView(SuccessResponseMixin, generics.RetrieveUpdateDestroyAPIView):
    """Admin CRUD: retrieve, update, or remove partner driving teachers."""
    permission_classes = [IsAuthenticated, IsAdminLevel]
    serializer_class = PartnerTeacherAdminSerializer
    queryset = PartnerTeacher.objects.all()


class AdminCategoryPriceListCreateView(SuccessResponseMixin, generics.ListCreateAPIView):
    """Admin CRUD: list and configure pricing per license category."""
    permission_classes = [IsAuthenticated, IsSystemAdmin]
    serializer_class = CategoryPriceSerializer
    queryset = CategoryPrice.objects.all().order_by("category")


class AdminCategoryPriceDetailView(SuccessResponseMixin, generics.RetrieveUpdateDestroyAPIView):
    """Admin CRUD: retrieve, update, or delete category pricing."""
    permission_classes = [IsAuthenticated, IsSystemAdmin]
    serializer_class = CategoryPriceSerializer
    queryset = CategoryPrice.objects.all()
