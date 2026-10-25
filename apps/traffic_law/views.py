from rest_framework import viewsets, filters, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Q

from .models import (
    TrafficLawArticle,
    TrafficLawDefinition,
    TrafficSign,
    RoadMarking,
    PoliceEvaluationQuestion,
    TrafficQuestion,
)
from .serializers import (
    TrafficLawArticleListSerializer,
    TrafficLawArticleDetailSerializer,
    TrafficLawDefinitionSerializer,
    TrafficSignSerializer,
    RoadMarkingSerializer,
    PoliceEvaluationQuestionSerializer,
    TrafficQuestionSerializer,
)


class TrafficLawArticleViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only endpoint for statutory articles (Ingingo 1 to 159 + 47 bis + 56 bis).
    Lookup can be by article_code (e.g. 'art_1', 'art_47_bis') or primary key.
    """

    queryset = TrafficLawArticle.objects.all().order_by("article_number")
    permission_classes = [permissions.AllowAny]
    filter_backends = [filters.SearchFilter]
    search_fields = ["title", "content", "article_label"]
    lookup_field = "article_code"

    def get_serializer_class(self):
        if self.action == "retrieve":
            return TrafficLawArticleDetailSerializer
        return TrafficLawArticleListSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        part = self.request.query_params.get("part")
        if part:
            qs = qs.filter(part_number=part)
        return qs


class TrafficLawDefinitionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only endpoint for the 43 statutory definitions from Article 2.
    """

    queryset = TrafficLawDefinition.objects.select_related("article").order_by("number")
    serializer_class = TrafficLawDefinitionSerializer
    permission_classes = [permissions.AllowAny]
    filter_backends = [filters.SearchFilter]
    search_fields = ["term_rw", "term_fr", "term_en", "definition_rw"]


class TrafficSignViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only endpoint for official traffic signs (64 items).
    Supports filtering by category (WARNING, PRIORITY, PROHIBITORY, MANDATORY, INFORMATORY).
    """

    queryset = TrafficSign.objects.prefetch_related("related_articles").order_by("code")
    serializer_class = TrafficSignSerializer
    permission_classes = [permissions.AllowAny]
    filter_backends = [filters.SearchFilter]
    search_fields = ["code", "name_rw", "name_fr", "description_rw"]
    lookup_field = "code"

    def get_queryset(self):
        qs = super().get_queryset()
        category = self.request.query_params.get("category")
        if category:
            qs = qs.filter(category__iexact=category)
        return qs


class RoadMarkingViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only endpoint for road surface markings (16 items).
    """

    queryset = RoadMarking.objects.prefetch_related("related_articles").order_by("marking_code")
    serializer_class = RoadMarkingSerializer
    permission_classes = [permissions.AllowAny]
    filter_backends = [filters.SearchFilter]
    search_fields = ["marking_code", "name_rw", "rule_rw"]
    lookup_field = "marking_code"


class PoliceEvaluationQuestionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only endpoint for official police magazine evaluation Q&As (220 items).
    """

    queryset = PoliceEvaluationQuestion.objects.prefetch_related("related_articles").order_by("question_number")
    serializer_class = PoliceEvaluationQuestionSerializer
    permission_classes = [permissions.AllowAny]
    filter_backends = [filters.SearchFilter]
    search_fields = ["question_rw", "answer_rw"]

    def get_queryset(self):
        qs = super().get_queryset()
        article = self.request.query_params.get("article")
        if article:
            qs = qs.filter(related_articles__article_code=article)
        return qs


class TrafficQuestionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only endpoint for companion driving test questions (401 items).
    Supports domain filtering and random sample selection.
    """

    queryset = TrafficQuestion.objects.prefetch_related("related_articles").order_by("question_number")
    serializer_class = TrafficQuestionSerializer
    permission_classes = [permissions.AllowAny]
    filter_backends = [filters.SearchFilter]
    search_fields = ["question_text_rw", "question_text_en", "question_text_fr"]

    def get_queryset(self):
        qs = super().get_queryset()
        domain = self.request.query_params.get("domain")
        if domain:
            qs = qs.filter(domain_tags__contains=domain)
        has_image = self.request.query_params.get("has_image")
        if has_image is not None:
            if has_image.lower() in ("true", "1"):
                qs = qs.exclude(Q(image="") | Q(image__isnull=True))
            elif has_image.lower() in ("false", "0"):
                qs = qs.filter(Q(image="") | Q(image__isnull=True))
        return qs


class TrafficLawSummaryStatsView(APIView):
    """
    Provides overall summary statistics for the traffic law legal corpus.
    """

    permission_classes = [permissions.AllowAny]

    def get(self, request, *args, **kwargs):
        return Response({
            "corpus": "Rwanda Traffic Law (Presidential Order No. 85/01 of 02/09/2002)",
            "official_gazette": "Year 41 No. 22 of 15 November 2002",
            "stats": {
                "total_articles": TrafficLawArticle.objects.count(),
                "total_definitions": TrafficLawDefinition.objects.count(),
                "total_traffic_signs": TrafficSign.objects.count(),
                "total_road_markings": RoadMarking.objects.count(),
                "total_police_evaluations": PoliceEvaluationQuestion.objects.count(),
                "total_practice_questions": TrafficQuestion.objects.count(),
            }
        })
