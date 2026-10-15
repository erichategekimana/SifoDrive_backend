"""
apps/lms/models/__init__.py
============================
Public re-export surface for the LMS models package.

All models are accessible via `from apps.lms.models import <Model>` — exactly
as before the package split. No existing import anywhere in the project needs
to change.

Domain layout:
  choices.py    → TextChoices / enumerations
  curriculum.py → Curriculum, Course
  content.py    → RoadSign, Module, Lesson, LessonQuestion
  quiz.py       → QuizQuestion, Quiz, QuizQuestionItem
  progress.py   → StudentProgress, LessonBookmark
"""

# Enumerations
from apps.lms.models.choices import (  # noqa: F401
    CorrectOption,
    Difficulty,
    LessonType,
    LessonContentType,
    DocumentFormat,
    QuizDomain,
    QuizType,
    RoadSignCategory,
)

# Curriculum layer
from apps.lms.models.curriculum import (  # noqa: F401
    Curriculum,
    Course,
)

# Content layer
from apps.lms.models.content import (  # noqa: F401
    RoadSign,
    Module,
    Lesson,
    LessonContent,
    LessonQuestion,
)

# Quiz layer
from apps.lms.models.quiz import (  # noqa: F401
    QuizQuestion,
    Quiz,
    QuizQuestionItem,
    QuizSubmission,
)

# Progress / engagement layer
from apps.lms.models.progress import (  # noqa: F401
    StudentProgress,
    LessonBookmark,
)

# Support / help tickets layer
from apps.lms.models.support import (  # noqa: F401
    HelpTicket,
    TicketCategory,
    TicketFeedbackRating,
    TicketFeedbackResolution,
    TicketPriority,
    TicketRecipientRole,
    TicketStatus,
)

# Assignments layer
from apps.lms.models.assignments import (  # noqa: F401
    TutorCurriculumAssignment,
    TutorCourseAssignment,
)

# Cohort content controls
from apps.lms.models.cohort_content import (  # noqa: F401
    CohortModuleRelease,
    CohortQuizSchedule,
)

# Cohort activities layer
from apps.lms.models.activity import (  # noqa: F401
    ActivityType,
    ActivitySubmissionType,
    CohortActivity,
    StudentActivitySubmission,
)

# Announcements layer
from apps.lms.models.announcement import (  # noqa: F401
    AnnouncementTargetType,
    Announcement,
)

# Discussions layer
from apps.lms.models.discussion import (  # noqa: F401
    DiscussionTopic,
    DiscussionReply,
)

# Groups & Group Chat layer
from apps.lms.models.group import (  # noqa: F401
    CourseGroup,
    CourseGroupMessage,
)

__all__ = [
    # Choices
    "CorrectOption",
    "Difficulty",
    "LessonType",
    "QuizDomain",
    "QuizType",
    "RoadSignCategory",
    # Curriculum
    "Curriculum",
    "Course",
    # Content
    "RoadSign",
    "Module",
    "Lesson",
    "LessonQuestion",
    # Quiz
    "QuizQuestion",
    "Quiz",
    "QuizQuestionItem",
    "QuizSubmission",
    # Progress
    "StudentProgress",
    "LessonBookmark",
    # Support
    "HelpTicket",
    "TicketCategory",
    "TicketPriority",
    "TicketRecipientRole",
    "TicketStatus",
    # Assignments
    "TutorCurriculumAssignment",
    "TutorCourseAssignment",
    # Cohort content
    "CohortModuleRelease",
    "CohortQuizSchedule",
    # Cohort activities
    "ActivityType",
    "ActivitySubmissionType",
    "CohortActivity",
    "StudentActivitySubmission",
    # Announcements
    "AnnouncementTargetType",
    "Announcement",
    # Discussions
    "DiscussionTopic",
    "DiscussionReply",
    # Course Groups
    "CourseGroup",
    "CourseGroupMessage",
]

