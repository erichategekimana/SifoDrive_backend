"""
apps/lms/urls.py
=================
LMS URL routes — prefixed with /api/v1/lms/ in config/urls.py.

Endpoint summary:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
COURSES
  GET   courses/                        Course catalogue (auth required)
  POST  courses/                        Create course  [Tutor+Admin]
  GET   courses/<id>/                   Course detail
  PATCH courses/<id>/                   Edit course    [Tutor+Admin]
  DELETE courses/<id>/                  Delete course  [Admin]
  POST  courses/<id>/publish/           Publish        [Admin]
  POST  courses/<id>/unpublish/         Unpublish      [Admin]
  GET   courses/<id>/stats/             Stats          [Tutor+Admin]
  GET   courses/<id>/modules/           Module list for course

MODULES
  POST  modules/                        Create module  [Tutor+Admin]
  GET   modules/<id>/                   Module detail
  PATCH modules/<id>/                   Edit module    [Tutor+Admin]
  DELETE modules/<id>/                  Delete module  [Admin]
  POST  modules/<id>/publish/           Publish        [Admin]
  POST  modules/<id>/unpublish/         Unpublish      [Admin]
  GET   modules/<id>/lessons/           Lesson list for module

LESSONS
  POST  lessons/                        Create lesson  [Tutor+Admin]
  GET   lessons/<id>/                   Lesson detail
  PATCH lessons/<id>/                   Edit lesson    [Tutor+Admin]
  DELETE lessons/<id>/                  Delete lesson  [Admin]
  GET   lessons/<id>/questions/         Quiz questions for lesson
  POST  lessons/<id>/questions/         Add question   [Tutor+Admin]
  DELETE lessons/<id>/questions/<qid>/  Remove question [Tutor+Admin]

ROAD SIGNS
  GET   road-signs/                     Sign reference browser
  POST  road-signs/                     Add sign       [Tutor+Admin]
  GET   road-signs/<id>/                Sign detail
  PATCH road-signs/<id>/                Edit sign      [Admin]

QUIZ QUESTIONS
  GET   questions/                      Question bank  [Student+]
  POST  questions/                      Create question [Tutor+Admin]
  GET   questions/<id>/                 Question detail [Student+]
  PATCH questions/<id>/                 Edit question  [Tutor+Admin]

PROGRESS
  GET   progress/                       My progress list
  POST  progress/complete/              Mark lesson complete  [Student]
  POST  progress/quiz/                  Record quiz attempt  [Student]
  GET   progress/summary/              Dashboard summary

BOOKMARKS
  GET   bookmarks/                      My bookmarks
  POST  bookmarks/                      Add bookmark
  DELETE bookmarks/<id>/                Remove bookmark
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

from django.urls import path

from .views import (
    BookmarkCreateView,
    BookmarkDeleteView,
    BookmarkListView,
    CourseCreateView,
    CourseDeleteView,
    CourseDetailView,
    CourseListView,
    CoursePublishView,
    CourseStatsView,
    CourseUnpublishView,
    CourseUpdateView,
    LessonCreateView,
    LessonDeleteView,
    LessonDetailView,
    LessonListView,
    LessonQuestionAddView,
    LessonQuestionListView,
    LessonQuestionRemoveView,
    LessonUpdateView,
    MarkLessonCompleteView,
    ModuleCreateView,
    ModuleDeleteView,
    ModuleDetailView,
    ModuleListView,
    ModulePublishView,
    ModuleUnpublishView,
    ModuleUpdateView,
    ProgressListView,
    ProgressSummaryView,
    QuizQuestionCreateView,
    QuizQuestionDetailView,
    QuizQuestionListView,
    QuizQuestionUpdateView,
    RecordQuizAttemptView,
    RoadSignCreateView,
    RoadSignDetailView,
    RoadSignListView,
    RoadSignUpdateView,
)

app_name = "lms"

urlpatterns = [

    # ── Courses ──────────────────────────────────────────────────────────────
    path("courses/",                            CourseListView.as_view(),      name="course-list"),
    path("courses/create/",                     CourseCreateView.as_view(),    name="course-create"),
    path("courses/<uuid:pk>/",                  CourseDetailView.as_view(),    name="course-detail"),
    path("courses/<uuid:pk>/edit/",             CourseUpdateView.as_view(),    name="course-update"),
    path("courses/<uuid:pk>/delete/",           CourseDeleteView.as_view(),    name="course-delete"),
    path("courses/<uuid:pk>/publish/",          CoursePublishView.as_view(),   name="course-publish"),
    path("courses/<uuid:pk>/unpublish/",        CourseUnpublishView.as_view(), name="course-unpublish"),
    path("courses/<uuid:pk>/stats/",            CourseStatsView.as_view(),     name="course-stats"),
    path("courses/<uuid:course_id>/modules/",   ModuleListView.as_view(),      name="course-modules"),

    # ── Modules ──────────────────────────────────────────────────────────────
    path("modules/",                            ModuleCreateView.as_view(),    name="module-create"),
    path("modules/<uuid:pk>/",                  ModuleDetailView.as_view(),    name="module-detail"),
    path("modules/<uuid:pk>/edit/",             ModuleUpdateView.as_view(),    name="module-update"),
    path("modules/<uuid:pk>/delete/",           ModuleDeleteView.as_view(),    name="module-delete"),
    path("modules/<uuid:pk>/publish/",          ModulePublishView.as_view(),   name="module-publish"),
    path("modules/<uuid:pk>/unpublish/",        ModuleUnpublishView.as_view(), name="module-unpublish"),
    path("modules/<uuid:module_id>/lessons/",   LessonListView.as_view(),      name="module-lessons"),

    # ── Lessons ──────────────────────────────────────────────────────────────
    path("lessons/",                            LessonCreateView.as_view(),           name="lesson-create"),
    path("lessons/<uuid:pk>/",                  LessonDetailView.as_view(),           name="lesson-detail"),
    path("lessons/<uuid:pk>/edit/",             LessonUpdateView.as_view(),           name="lesson-update"),
    path("lessons/<uuid:pk>/delete/",           LessonDeleteView.as_view(),           name="lesson-delete"),
    path("lessons/<uuid:lesson_id>/questions/", LessonQuestionListView.as_view(),     name="lesson-questions"),
    path("lessons/<uuid:lesson_id>/questions/add/",   LessonQuestionAddView.as_view(),    name="lesson-question-add"),
    path("lessons/<uuid:lesson_id>/questions/<uuid:question_id>/remove/",
         LessonQuestionRemoveView.as_view(), name="lesson-question-remove"),

    # ── Road Signs ───────────────────────────────────────────────────────────
    path("road-signs/",            RoadSignListView.as_view(),   name="roadsign-list"),
    path("road-signs/create/",     RoadSignCreateView.as_view(), name="roadsign-create"),
    path("road-signs/<uuid:pk>/",  RoadSignDetailView.as_view(), name="roadsign-detail"),
    path("road-signs/<uuid:pk>/edit/", RoadSignUpdateView.as_view(), name="roadsign-update"),

    # ── Quiz Questions ───────────────────────────────────────────────────────
    path("questions/",            QuizQuestionListView.as_view(),   name="question-list"),
    path("questions/create/",     QuizQuestionCreateView.as_view(), name="question-create"),
    path("questions/<uuid:pk>/",  QuizQuestionDetailView.as_view(), name="question-detail"),
    path("questions/<uuid:pk>/edit/", QuizQuestionUpdateView.as_view(), name="question-update"),

    # ── Student Progress ─────────────────────────────────────────────────────
    path("progress/",          ProgressListView.as_view(),        name="progress-list"),
    path("progress/complete/", MarkLessonCompleteView.as_view(),  name="progress-complete"),
    path("progress/quiz/",     RecordQuizAttemptView.as_view(),   name="progress-quiz"),
    path("progress/summary/",  ProgressSummaryView.as_view(),     name="progress-summary"),

    # ── Bookmarks ─────────────────────────────────────────────────────────────
    path("bookmarks/",            BookmarkListView.as_view(),   name="bookmark-list"),
    path("bookmarks/add/",        BookmarkCreateView.as_view(), name="bookmark-create"),
    path("bookmarks/<uuid:pk>/",  BookmarkDeleteView.as_view(), name="bookmark-delete"),
]
