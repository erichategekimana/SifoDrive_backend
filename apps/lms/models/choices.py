"""
apps/lms/models/choices.py
===========================
All TextChoices / enumeration classes for the LMS domain.
Centralised here so they can be imported from models, serializers, and views
without creating circular dependencies.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _


class LessonType(models.TextChoices):
    TEXT       = "TEXT",      _("Text Article")
    AUDIO      = "AUDIO",     _("Audio Lesson")
    VIDEO      = "VIDEO",     _("Video Lesson")
    ROAD_SIGN  = "ROAD_SIGN", _("Road Sign Study")
    QUIZ       = "QUIZ",      _("Interactive Quiz")
    MULTI      = "MULTI",     _("Multi-Content Lesson")


class LessonContentType(models.TextChoices):
    TEXT         = "TEXT",         _("Text (Input / Article)")
    AUDIO        = "AUDIO",        _("Audio Recording")
    VIDEO        = "VIDEO",        _("Video Lecture")
    IMAGE        = "IMAGE",        _("Image / Infographic")
    DOCUMENT     = "DOCUMENT",     _("Text File / Presentation (PDF, PPT, Canva, Slides)")


class DocumentFormat(models.TextChoices):
    PDF          = "PDF",          _("PDF Document")
    POWERPOINT   = "POWERPOINT",   _("MS PowerPoint Presentation (.ppt, .pptx)")
    PRESENTATION = "PRESENTATION", _("Interactive Presentation / Slides")
    CANVA        = "CANVA",        _("Canva Design / Slides")
    OTHER        = "OTHER",        _("Other Document")



class RoadSignCategory(models.TextChoices):
    WARNING      = "WARNING",      _("Warning Signs (Yellow/Triangle)")
    PROHIBITORY  = "PROHIBITORY",  _("Prohibitory Signs (Red/Circle)")
    MANDATORY    = "MANDATORY",    _("Mandatory Signs (Blue/Circle)")
    INFORMATORY  = "INFORMATORY",  _("Informatory Signs (Blue/Rectangle)")
    ROAD_MARKING = "ROAD_MARKING", _("Road Markings")


class QuizDomain(models.TextChoices):
    PRIORITY = "PRIORITY", _("Priority Rules & Intersections")
    SIGNAGE  = "SIGNAGE",  _("Traffic Signage & Road Markings")
    SPEED    = "SPEED",    _("Speed Limits & Overtaking")
    LEGAL    = "LEGAL",    _("Legal Framework & Penalties")
    SAFETY   = "SAFETY",   _("Vehicle Safety & First Aid")
    PARKING  = "PARKING",  _("Parking & Stopping Rules")


class Difficulty(models.TextChoices):
    EASY   = "EASY",   _("Easy")
    MEDIUM = "MEDIUM", _("Medium")
    HARD   = "HARD",   _("Hard")


class CorrectOption(models.TextChoices):
    A = "A", "A"
    B = "B", "B"
    C = "C", "C"
    D = "D", "D"
