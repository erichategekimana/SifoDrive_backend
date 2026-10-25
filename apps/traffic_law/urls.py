from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    TrafficLawArticleViewSet,
    TrafficLawDefinitionViewSet,
    TrafficSignViewSet,
    RoadMarkingViewSet,
    PoliceEvaluationQuestionViewSet,
    TrafficQuestionViewSet,
    TrafficLawSummaryStatsView,
)

app_name = "traffic_law"

router = DefaultRouter()
router.register(r"articles", TrafficLawArticleViewSet, basename="article")
router.register(r"definitions", TrafficLawDefinitionViewSet, basename="definition")
router.register(r"signs", TrafficSignViewSet, basename="sign")
router.register(r"markings", RoadMarkingViewSet, basename="marking")
router.register(r"evaluations", PoliceEvaluationQuestionViewSet, basename="evaluation")
router.register(r"questions", TrafficQuestionViewSet, basename="question")

urlpatterns = [
    path("stats/", TrafficLawSummaryStatsView.as_view(), name="stats"),
    path("", include(router.urls)),
]
