"""
apps/lms/views/__init__.py
============================
Public re-export surface for the LMS views package.

All view classes remain importable from `apps.lms.views` — existing url.py
imports are unchanged.

Domain layout:
  curriculum_views.py  → Curriculum + Course views
  content_views.py     → Module, Lesson, LessonQuestion, RoadSign views
  quiz_views.py        → QuizQuestion bank + Quiz management views
  progress_views.py    → StudentProgress + Bookmark views
"""

from apps.lms.views.curriculum_views import (  # noqa: F401
    CurriculumListView,
    CurriculumCreateView,
    CurriculumDetailView,
    CurriculumUpdateView,
    CurriculumDeleteView,
    CurriculumPublishView,
    CurriculumUnpublishView,
    CurriculumCoursesListView,
    CourseListView,
    CourseCreateView,
    CourseDetailView,
    CourseUpdateView,
    CourseDeleteView,
    CoursePublishView,
    CourseUnpublishView,
    CourseStatsView,
)

from apps.lms.views.content_views import (  # noqa: F401
    ModuleListView,
    ModuleCreateView,
    ModuleDetailView,
    ModuleUpdateView,
    ModuleDeleteView,
    ModulePublishView,
    ModuleUnpublishView,
    LessonListView,
    LessonCreateView,
    LessonDetailView,
    LessonUpdateView,
    LessonDeleteView,
    LessonQuestionListView,
    LessonQuestionAddView,
    LessonQuestionRemoveView,
    RoadSignListView,
    RoadSignDetailView,
    RoadSignCreateView,
    RoadSignUpdateView,
)

from apps.lms.views.quiz_views import (  # noqa: F401
    QuizQuestionListView,
    QuizQuestionDetailView,
    QuizQuestionCreateView,
    QuizQuestionUpdateView,
    QuizListCreateView,
    QuizDetailUpdateDeleteView,
    QuizPublishToggleView,
)

from apps.lms.views.progress_views import (  # noqa: F401
    ProgressListView,
    MarkLessonCompleteView,
    RecordQuizAttemptView,
    ProgressSummaryView,
    BookmarkListView,
    BookmarkCreateView,
    BookmarkDeleteView,
)

from apps.lms.views.support_views import (  # noqa: F401
    HelpTicketListCreateView,
    HelpTicketDetailView,
    SupportAnnouncementsView,
)

from apps.lms.views.tutor_assignment_views import (  # noqa: F401
    AdminTutorsListView,
    AdminTutorCurriculaAssignmentView,
    AdminTutorCoursesAssignmentView,
)

from apps.lms.views.cohort_material_views import (  # noqa: F401
    TutorAssignedCohortsListView,
    TutorCohortCoursesListView,
    TutorCohortModulesView,
    TutorCohortModuleReleaseUpdateView,
    TutorCohortQuizzesView,
    TutorCohortQuizScheduleView,
    TutorCohortQuizExtendView,
    TutorApproachingDeadlinesView,
)

from apps.lms.views.activity_views import (  # noqa: F401
    TutorCohortActivitiesListCreateView,
    TutorCohortActivityDetailUpdateDeleteView,
    TutorCohortActivitySubmissionsListView,
    TutorCohortActivityGradeSubmissionView,
    StudentCohortActivitiesListView,
    StudentCohortActivitySubmitView,
)


