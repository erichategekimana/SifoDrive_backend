"""
apps/lms/admin.py
==================
Django Admin configuration for the LMS app.

Admin design principles:
  - SYSTEM_ADMIN has full control over all models.
  - Tutors are represented by Django staff accounts with limited permissions.
  - Inline editors let admins manage Course → Module → Lesson in one place.
  - Publish/unpublish via custom actions (no direct field toggle).
  - Read-only fields prevent accidental data corruption.
"""

from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import (
    CohortActivity,
    CohortModuleRelease,
    CohortQuizSchedule,
    Course,
    Curriculum,
    HelpTicket,
    Lesson,
    LessonBookmark,
    LessonQuestion,
    Module,
    Quiz,
    QuizQuestion,
    QuizQuestionItem,
    RoadSign,
    StudentActivitySubmission,
    StudentProgress,
    TutorCourseAssignment,
    TutorCurriculumAssignment,
)


# ===========================================================================
# Inline editors (used inside parent admin pages)
# ===========================================================================

class CourseInline(admin.TabularInline):
    """Courses inline inside Curriculum admin."""

    model = Course
    extra = 0
    fields = ["title", "code", "sort_order", "estimated_hours", "is_published"]
    readonly_fields = ["is_published"]
    ordering = ["sort_order"]
    show_change_link = True


class ModuleInline(admin.TabularInline):
    """Modules inline inside Course admin."""

    model  = Module
    extra  = 0
    fields = ["title", "sort_order", "is_foundational", "is_published"]
    readonly_fields = ["is_published"]
    ordering = ["sort_order"]
    show_change_link = True


class LessonInline(admin.TabularInline):
    """Lessons inline inside Module admin."""

    model  = Lesson
    extra  = 0
    fields = ["title", "lesson_type", "sort_order", "is_free_preview", "is_student_only", "duration_minutes"]
    ordering = ["sort_order"]
    show_change_link = True


class LessonQuestionInline(admin.TabularInline):
    """Questions inline inside QuizQuestion lesson admin."""

    model  = LessonQuestion
    extra  = 1
    fields = ["question", "sort_order"]
    ordering = ["sort_order"]
    autocomplete_fields = ["question"]


# ===========================================================================
# Curriculum Admin
# ===========================================================================

@admin.register(Curriculum)
class CurriculumAdmin(admin.ModelAdmin):
    list_display = [
        "title", "code", "publish_status", "course_count",
        "sort_order", "created_by", "created_at",
    ]
    list_filter = ["is_published", "created_at"]
    search_fields = ["title", "title_kinyarwanda", "code", "description"]
    ordering = ["sort_order", "title"]
    readonly_fields = [
        "id", "published_at", "published_by", "created_by", "updated_by",
        "created_at", "updated_at",
    ]
    inlines = [CourseInline]

    @admin.display(description=_("Status"))
    def publish_status(self, obj):
        if obj.is_published:
            return format_html('<span style="color:#16a34a; font-weight:bold;">● Live</span>')
        return format_html('<span style="color:#d97706;">○ Draft</span>')

    @admin.display(description=_("Courses"))
    def course_count(self, obj):
        return obj.course_count


# ===========================================================================
# Course Admin
# ===========================================================================

@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = [
        "title", "code", "curriculum", "publish_status", "module_count", "lesson_count",
        "estimated_hours", "sort_order", "created_by", "created_at",
    ]
    list_filter  = ["is_published", "curriculum", "created_at"]
    search_fields = ["title", "title_kinyarwanda", "code", "description"]
    ordering = ["sort_order", "title"]
    readonly_fields = [
        "id", "published_at", "published_by", "created_by", "updated_by",
        "created_at", "updated_at",
    ]
    inlines = [ModuleInline]
    actions = ["publish_selected", "unpublish_selected"]

    fieldsets = (
        (_("Content"), {
            "fields": ("title", "description", "thumbnail", "estimated_hours", "sort_order"),
        }),
        (_("Publish State"), {
            "fields": ("is_published", "published_at", "published_by"),
        }),
        (_("Authorship"), {
            "fields": ("created_by", "updated_by"),
            "classes": ("collapse",),
        }),
        (_("System"), {
            "fields": ("id", "created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    @admin.display(description=_("Status"))
    def publish_status(self, obj):
        if obj.is_published:
            return format_html('<span style="color:#16a34a; font-weight:bold;">● Live</span>')
        return format_html('<span style="color:#d97706;">○ Draft</span>')

    @admin.display(description=_("Modules"))
    def module_count(self, obj):
        return obj.modules.filter(is_deleted=False).count()

    @admin.display(description=_("Lessons"))
    def lesson_count(self, obj):
        return obj.lesson_count

    @admin.action(description=_("✓ Publish selected courses"))
    def publish_selected(self, request, queryset):
        published = 0
        for course in queryset:
            try:
                from .services import CourseService
                CourseService.publish_course(course, published_by=request.user)
                published += 1
            except ValueError as exc:
                self.message_user(request, f"'{course.title}': {exc}", level="warning")
        if published:
            self.message_user(request, f"{published} course(s) published successfully.")

    @admin.action(description=_("○ Unpublish selected courses"))
    def unpublish_selected(self, request, queryset):
        queryset.update(is_published=False)
        self.message_user(request, f"{queryset.count()} course(s) moved to draft.")


# ===========================================================================
# Module Admin
# ===========================================================================

@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    list_display = [
        "title", "course", "is_foundational", "publish_status",
        "lesson_count", "sort_order",
    ]
    list_filter  = ["is_published", "is_foundational", "course"]
    search_fields = ["title", "course__title"]
    ordering = ["course__sort_order", "sort_order"]
    readonly_fields = ["id", "published_at", "published_by", "created_at", "updated_at"]
    inlines = [LessonInline]
    actions = ["publish_selected", "unpublish_selected", "mark_foundational", "unmark_foundational"]

    fieldsets = (
        (_("Content"), {
            "fields": ("course", "title", "description", "sort_order"),
        }),
        (_("Flags"), {
            "fields": ("is_foundational",),
        }),
        (_("Publish State"), {
            "fields": ("is_published", "published_at", "published_by"),
        }),
        (_("System"), {
            "fields": ("id", "created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    @admin.display(description=_("Status"))
    def publish_status(self, obj):
        if obj.is_published:
            return format_html('<span style="color:#16a34a;">● Live</span>')
        return format_html('<span style="color:#d97706;">○ Draft</span>')

    @admin.display(description=_("Lessons"))
    def lesson_count(self, obj):
        return obj.lessons.filter(is_deleted=False).count()

    @admin.action(description=_("✓ Publish selected modules"))
    def publish_selected(self, request, queryset):
        for module in queryset:
            try:
                from .services import CourseService
                CourseService.publish_module(module, published_by=request.user)
            except ValueError as exc:
                self.message_user(request, f"'{module.title}': {exc}", level="warning")

    @admin.action(description=_("○ Unpublish selected modules"))
    def unpublish_selected(self, request, queryset):
        queryset.update(is_published=False)

    @admin.action(description=_("★ Mark as Foundational"))
    def mark_foundational(self, request, queryset):
        queryset.update(is_foundational=True)

    @admin.action(description=_("☆ Remove Foundational flag"))
    def unmark_foundational(self, request, queryset):
        queryset.update(is_foundational=False)


# ===========================================================================
# Lesson Admin
# ===========================================================================

@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = [
        "title", "module", "lesson_type", "sort_order",
        "access_flags", "duration_minutes",
    ]
    list_filter  = ["lesson_type", "is_free_preview", "is_student_only", "module__course"]
    search_fields = ["title", "module__title", "module__course__title"]
    ordering = ["module__course__sort_order", "module__sort_order", "sort_order"]
    readonly_fields = ["id", "created_at", "updated_at"]
    inlines = [LessonQuestionInline]

    fieldsets = (
        (_("Identity"), {
            "fields": ("module", "title", "lesson_type", "sort_order"),
        }),
        (_("Content"), {
            "fields": ("content_text", "media_file", "media_url", "road_sign", "duration_minutes"),
        }),
        (_("Access Control"), {
            "fields": ("is_free_preview", "is_student_only"),
            "description": _(
                "is_free_preview: guests can see this lesson. "
                "is_student_only: only enrolled students can see this lesson."
            ),
        }),
        (_("System"), {
            "fields": ("id", "created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    @admin.display(description=_("Access"))
    def access_flags(self, obj):
        flags = []
        if obj.is_free_preview:
            flags.append(format_html('<span style="color:#2563eb;">👁 Preview</span>'))
        if obj.is_student_only:
            flags.append(format_html('<span style="color:#7c3aed;">🎓 Students</span>'))
        return format_html(" &nbsp;".join(flags)) if flags else "—"


# ===========================================================================
# Road Sign Admin
# ===========================================================================

@admin.register(RoadSign)
class RoadSignAdmin(admin.ModelAdmin):
    list_display  = ["name", "sign_code", "category", "sign_thumbnail", "is_active"]
    list_filter   = ["category", "is_active"]
    search_fields = ["name", "sign_code", "description"]
    ordering = ["category", "name"]
    readonly_fields = ["id", "created_at", "updated_at"]

    fieldsets = (
        (_("Identity"), {
            "fields": ("name", "sign_code", "category", "is_active"),
        }),
        (_("Visual"), {
            "fields": ("image",),
        }),
        (_("Description"), {
            "fields": ("description", "description_kinyarwanda"),
        }),
        (_("System"), {
            "fields": ("id", "created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    @admin.display(description=_("Image"))
    def sign_thumbnail(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="height:40px; border-radius:4px;" />',
                obj.image.url,
            )
        return "—"


# ===========================================================================
# Quiz Question Admin
# ===========================================================================

@admin.register(QuizQuestion)
class QuizQuestionAdmin(admin.ModelAdmin):
    list_display  = ["question_number", "short_question", "domain", "difficulty", "correct_option", "has_image", "is_active", "created_by"]
    list_filter   = ["domain", "difficulty", "is_active"]
    search_fields = ["question_number", "question_text_kinyarwanda", "question_text"]
    ordering = ["question_number", "domain", "difficulty"]
    readonly_fields = ["id", "created_by", "created_at", "updated_at", "image_preview", "option_images_preview"]
    autocomplete_fields = ["road_sign"]
    actions = ["activate_questions", "deactivate_questions"]

    fieldsets = (
        (_("Question Reference"), {
            "fields": ("question_number", "domain", "difficulty", "road_sign", "is_active"),
        }),
        (_("Question Prompts"), {
            "fields": ("question_text_kinyarwanda", "question_text"),
        }),
        (_("Prompt Diagram"), {
            "fields": ("image", "image_preview"),
        }),
        (_("Answer Options (Kinyarwanda)"), {
            "fields": ("option_a_kinyarwanda", "option_b_kinyarwanda", "option_c_kinyarwanda", "option_d_kinyarwanda"),
        }),
        (_("Answer Options (English)"), {
            "fields": ("option_a", "option_b", "option_c", "option_d"),
        }),
        (_("Image-based Answer Choices"), {
            "fields": ("option_a_image", "option_b_image", "option_c_image", "option_d_image", "option_images_preview"),
        }),
        (_("Correct Answer & Explanation"), {
            "fields": ("correct_option", "explanation_kinyarwanda", "explanation"),
        }),
        (_("System"), {
            "fields": ("id", "created_by", "created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    @admin.display(description=_("Question"))
    def short_question(self, obj):
        text = obj.question_text_kinyarwanda or obj.question_text or "—"
        return text[:80] + ("…" if len(text) > 80 else "")

    @admin.display(boolean=True, description=_("Diagram"))
    def has_image(self, obj):
        return bool(obj.image or obj.option_a_image)

    @admin.display(description=_("Prompt Diagram"))
    def image_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="max-height:160px; border-radius:6px; border:1px solid #e2e8f0;" />',
                obj.image.url,
            )
        return "No prompt diagram"

    @admin.display(description=_("Option Diagrams Preview"))
    def option_images_preview(self, obj):
        imgs = []
        for opt in ['a', 'b', 'c', 'd']:
            field = getattr(obj, f"option_{opt}_image")
            if field:
                imgs.append(
                    format_html(
                        '<div style="display:inline-block; margin-right:12px; text-align:center;">'
                        '<span style="display:block; font-weight:bold; margin-bottom:4px;">Option {}</span>'
                        '<img src="{}" style="max-height:90px; border-radius:4px; border:1px solid #cbd5e1; padding:2px;" />'
                        '</div>',
                        opt.upper(),
                        field.url,
                    )
                )
        return format_html("".join(imgs)) if imgs else "No option images"

    @admin.action(description=_("✓ Activate selected questions"))
    def activate_questions(self, request, queryset):
        queryset.update(is_active=True)

    @admin.action(description=_("✗ Deactivate selected questions"))
    def deactivate_questions(self, request, queryset):
        queryset.update(is_active=False)


# ===========================================================================
# Student Progress Admin (read-only)
# ===========================================================================

@admin.register(StudentProgress)
class StudentProgressAdmin(admin.ModelAdmin):
    list_display  = ["student", "lesson", "is_completed", "quiz_score", "quiz_attempts", "completed_at"]
    list_filter   = ["is_completed", "lesson__lesson_type", "lesson__module__course"]
    search_fields = ["student__phone_number", "lesson__title"]
    ordering = ["-updated_at"]
    readonly_fields = [f.name for f in StudentProgress._meta.get_fields() if hasattr(f, 'name')]

    def has_add_permission(self, request):    return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False


# ===========================================================================
# Bookmark Admin (read-only for support)
# ===========================================================================

@admin.register(LessonBookmark)
class LessonBookmarkAdmin(admin.ModelAdmin):
    list_display  = ["student", "lesson", "note", "created_at"]
    search_fields = ["student__phone_number", "lesson__title"]
    readonly_fields = ["id", "student", "lesson", "note", "created_at"]

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False


# ===========================================================================
# Quiz & QuizQuestionItem Admin
# ===========================================================================

class QuizQuestionItemInline(admin.StackedInline):
    model = QuizQuestionItem
    extra = 0
    fields = [
        "sort_order", "question_text", "question_text_kinyarwanda",
        "option_a", "option_b", "option_c", "option_d",
        "correct_option", "points", "domain", "difficulty", "original_question"
    ]
    autocomplete_fields = ["original_question"]
    ordering = ["sort_order"]


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = [
        "title", "course", "module", "is_published", "status_display",
        "total_score", "passing_score", "open_date", "deadline",
        "created_by", "created_at"
    ]
    list_filter = ["is_published", "course", "created_at"]
    search_fields = ["title", "title_kinyarwanda", "description", "rubric"]
    readonly_fields = ["created_at", "updated_at"]
    inlines = [QuizQuestionItemInline]

    @admin.display(description=_("Status"))
    def status_display(self, obj):
        st = obj.status
        colors = {
            "DRAFT": "#64748b",
            "SCHEDULED": "#d97706",
            "OPEN": "#16a34a",
            "CLOSED": "#dc2626",
        }
        return format_html('<span style="color:{}; font-weight:bold;">● {}</span>', colors.get(st, "#000"), st)


@admin.register(QuizQuestionItem)
class QuizQuestionItemAdmin(admin.ModelAdmin):
    list_display = ["quiz", "sort_order", "question_text", "correct_option", "points", "domain", "difficulty"]
    list_filter = ["quiz", "domain", "difficulty"]
    search_fields = ["question_text", "question_text_kinyarwanda", "quiz__title"]


@admin.register(HelpTicket)
class HelpTicketAdmin(admin.ModelAdmin):
    list_display = ["subject", "user", "recipient_role", "category", "priority", "status", "assigned_to", "created_at"]
    list_filter = ["status", "recipient_role", "category", "priority", "created_at"]
    search_fields = ["subject", "message", "user__phone_number", "user__first_name", "user__last_name"]
    readonly_fields = ["created_at", "updated_at"]


# ===========================================================================
# Tutor Assignments Admin
# ===========================================================================

@admin.register(TutorCurriculumAssignment)
class TutorCurriculumAssignmentAdmin(admin.ModelAdmin):
    list_display = ["tutor", "curriculum", "is_active", "assigned_by", "created_at"]
    list_filter = ["is_active", "curriculum"]
    search_fields = ["tutor__phone_number", "tutor__first_name", "tutor__last_name", "curriculum__title"]
    autocomplete_fields = ["tutor", "curriculum"]


@admin.register(TutorCourseAssignment)
class TutorCourseAssignmentAdmin(admin.ModelAdmin):
    list_display = ["tutor", "course", "is_active", "assigned_by", "created_at"]
    list_filter = ["is_active", "course__curriculum", "course"]
    search_fields = ["tutor__phone_number", "tutor__first_name", "tutor__last_name", "course__title"]
    autocomplete_fields = ["tutor", "course"]


# ===========================================================================
# Cohort Content Controls Admin
# ===========================================================================

@admin.register(CohortModuleRelease)
class CohortModuleReleaseAdmin(admin.ModelAdmin):
    list_display = ["cohort", "module", "is_published", "is_locked", "unlock_date", "updated_by", "updated_at"]
    list_filter = ["is_published", "is_locked", "cohort"]
    search_fields = ["cohort__name", "module__title"]


@admin.register(CohortQuizSchedule)
class CohortQuizScheduleAdmin(admin.ModelAdmin):
    list_display = ["cohort", "quiz", "is_published", "is_locked", "open_date", "deadline", "extended_deadline", "scheduled_by"]
    list_filter = ["is_published", "is_locked", "cohort"]
    search_fields = ["cohort__name", "quiz__title"]


# ===========================================================================
# Cohort Activities & Submissions Admin
# ===========================================================================

@admin.register(CohortActivity)
class CohortActivityAdmin(admin.ModelAdmin):
    list_display = ["title", "cohort", "course", "activity_type", "total_points", "due_date", "is_published", "is_locked"]
    list_filter = ["activity_type", "is_published", "is_locked", "cohort"]
    search_fields = ["title", "title_kinyarwanda", "description", "cohort__name"]


@admin.register(StudentActivitySubmission)
class StudentActivitySubmissionAdmin(admin.ModelAdmin):
    list_display = ["activity", "student", "status", "score", "submitted_at", "graded_by", "graded_at"]
    list_filter = ["status", "activity__cohort"]
    search_fields = ["activity__title", "student__phone_number", "student__first_name", "student__last_name"]
    readonly_fields = ["submitted_at"]


