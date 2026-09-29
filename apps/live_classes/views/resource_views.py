from rest_framework import generics
from rest_framework.exceptions import ValidationError

from apps.core.mixins import SuccessResponseMixin
from apps.core.permissions import (
    IsStudentOrStaff,
    IsTutorOrTrainingAdmin,
)
from apps.live_classes.models import ClassResource, LiveClass
from apps.live_classes.serializers import (
    ClassResourceCreateSerializer,
    ClassResourceSerializer,
)
from apps.live_classes.services import LiveClassService


class ClassResourceListCreateView(SuccessResponseMixin, generics.ListCreateAPIView):
    """
    GET: List supplementary materials for a live class.
    POST: Upload slide deck / add link (Tutor, Training Admin, System Admin).
    """

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsTutorOrTrainingAdmin()]
        return [IsStudentOrStaff()]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ClassResourceCreateSerializer
        return ClassResourceSerializer

    def get_queryset(self):
        return ClassResource.objects.filter(live_class_id=self.kwargs["pk"])

    def perform_create(self, serializer):
        try:
            live_class = LiveClass.objects.get(pk=self.kwargs["pk"])
        except LiveClass.DoesNotExist:
            raise ValidationError("Live class not found.")

        resource = LiveClassService.add_resource(
            live_class=live_class,
            title=serializer.validated_data["title"],
            file=serializer.validated_data.get("file"),
            external_link=serializer.validated_data.get("external_link", ""),
            description=serializer.validated_data.get("description", ""),
            uploaded_by=self.request.user,
        )
        serializer.instance = resource


class ClassResourceDetailView(SuccessResponseMixin, generics.DestroyAPIView):
    """DELETE: Remove an uploaded class resource (Tutor, Training Admin, Admin)."""

    permission_classes = [IsTutorOrTrainingAdmin]
    queryset = ClassResource.objects.all()
