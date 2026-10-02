"""
apps/lms/serializers/__init__.py
=================================
LMS serializers package.

Re-exports all serializers from domain modules for seamless backward compatibility:
- road_sign_serializers
- content_serializers
- quiz_serializers
- curriculum_serializers
- progress_serializers
"""

from .road_sign_serializers import (
    RoadSignSerializer,
)
from .quiz_serializers import (
    QuizQuestionListSerializer,
    QuizQuestionDetailSerializer,
    QuizQuestionWriteSerializer,
    QuizQuestionItemSerializer,
    QuizCreatorSerializer,
    QuizListSerializer,
    QuizDetailSerializer,
    QuizWriteSerializer,
)
from .content_serializers import (
    LessonListSerializer,
    LessonDetailSerializer,
    LessonWriteSerializer,
    LessonBookmarkSerializer,
    LessonQuestionSerializer,
)
from .curriculum_serializers import (
    ModuleListSerializer,
    ModuleDetailSerializer,
    ModuleWriteSerializer,
    CourseListSerializer,
    CourseDetailSerializer,
    CourseWriteSerializer,
    CourseStatsSerializer,
    CurriculumListSerializer,
    CurriculumDetailSerializer,
    CurriculumWriteSerializer,
)
from .progress_serializers import (
    StudentProgressSerializer,
    MarkLessonCompleteSerializer,
    RecordQuizAttemptSerializer,
    ProgressSummarySerializer,
)
from .support_serializers import (
    HelpTicketSerializer,
    HelpTicketCreateSerializer,
    HelpTicketResolveSerializer,
)

__all__ = [
    # Road Sign
    "RoadSignSerializer",
    # Quiz Question
    "QuizQuestionListSerializer",
    "QuizQuestionDetailSerializer",
    "QuizQuestionWriteSerializer",
    # Lesson
    "LessonListSerializer",
    "LessonDetailSerializer",
    "LessonWriteSerializer",
    "LessonBookmarkSerializer",
    "LessonQuestionSerializer",
    # Module
    "ModuleListSerializer",
    "ModuleDetailSerializer",
    "ModuleWriteSerializer",
    # Course
    "CourseListSerializer",
    "CourseDetailSerializer",
    "CourseWriteSerializer",
    "CourseStatsSerializer",
    # Curriculum
    "CurriculumListSerializer",
    "CurriculumDetailSerializer",
    "CurriculumWriteSerializer",
    # Progress
    "StudentProgressSerializer",
    "MarkLessonCompleteSerializer",
    "RecordQuizAttemptSerializer",
    "ProgressSummarySerializer",
    # Quiz
    "QuizQuestionItemSerializer",
    "QuizCreatorSerializer",
    "QuizListSerializer",
    "QuizDetailSerializer",
    "QuizWriteSerializer",
    # Support
    "HelpTicketSerializer",
    "HelpTicketCreateSerializer",
    "HelpTicketResolveSerializer",
]

