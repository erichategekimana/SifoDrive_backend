"""
apps/lms/serializers/quiz_serializers.py
=========================================
Serializers for quiz questions, quiz question items, and quizzes.
"""

from django.db import models, transaction
from rest_framework import serializers

from apps.accounts.constants import UserRole
from apps.lms.models.quiz import Quiz, QuizQuestion, QuizQuestionItem, QuizSubmission
from .road_sign_serializers import RoadSignSerializer


# ===========================================================================
# Quiz Question
# ===========================================================================

class QuizQuestionListSerializer(serializers.ModelSerializer):
    """Question bank list serializer with localized aliases and staff-aware answer exposure."""

    question_text_rw = serializers.CharField(source="question_text_kinyarwanda", read_only=True)
    option_a_rw = serializers.CharField(source="option_a_kinyarwanda", read_only=True)
    option_b_rw = serializers.CharField(source="option_b_kinyarwanda", read_only=True)
    option_c_rw = serializers.CharField(source="option_c_kinyarwanda", read_only=True)
    option_d_rw = serializers.CharField(source="option_d_kinyarwanda", read_only=True)
    explanation_rw = serializers.CharField(source="explanation_kinyarwanda", read_only=True)

    class Meta:
        model = QuizQuestion
        fields = [
            "id", "question_number", "domain", "difficulty",
            "question_text", "question_text_kinyarwanda", "question_text_rw",
            "option_a", "option_b", "option_c", "option_d",
            "option_a_kinyarwanda", "option_b_kinyarwanda", "option_c_kinyarwanda", "option_d_kinyarwanda",
            "option_a_rw", "option_b_rw", "option_c_rw", "option_d_rw",
            "correct_option", "explanation", "explanation_kinyarwanda", "explanation_rw",
            "image",
            "option_a_image", "option_b_image", "option_c_image", "option_d_image",
            "road_sign",
        ]
        read_only_fields = ["id"]

    def to_representation(self, instance):
        ret = super().to_representation(instance)
        request = self.context.get("request")
        user = getattr(request, "user", None)
        # Protect answer keys if accessed by regular students
        if user and getattr(user, "role", None) == UserRole.STUDENT:
            ret.pop("correct_option", None)
            ret.pop("explanation", None)
            ret.pop("explanation_kinyarwanda", None)
            ret.pop("explanation_rw", None)
        return ret


class QuizQuestionDetailSerializer(serializers.ModelSerializer):
    """Full serializer including correct answer — for tutors, admins, and post-quiz reveal."""

    correct_text = serializers.CharField(read_only=True)
    road_sign_detail = RoadSignSerializer(source="road_sign", read_only=True)

    class Meta:
        model = QuizQuestion
        fields = [
            "id", "question_number", "domain", "difficulty",
            "question_text", "question_text_kinyarwanda",
            "option_a", "option_b", "option_c", "option_d",
            "option_a_kinyarwanda", "option_b_kinyarwanda", "option_c_kinyarwanda", "option_d_kinyarwanda",
            "correct_option", "correct_text",
            "explanation", "explanation_kinyarwanda",
            "image",
            "option_a_image", "option_b_image", "option_c_image", "option_d_image",
            "road_sign", "road_sign_detail",
            "is_active", "created_by",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "correct_text"]


class QuizQuestionWriteSerializer(serializers.ModelSerializer):
    """Write serializer — used by tutors and admins to create/update questions."""

    class Meta:
        model = QuizQuestion
        fields = [
            "question_number", "domain", "difficulty",
            "question_text", "question_text_kinyarwanda",
            "option_a", "option_b", "option_c", "option_d",
            "option_a_kinyarwanda", "option_b_kinyarwanda", "option_c_kinyarwanda", "option_d_kinyarwanda",
            "correct_option", "explanation", "explanation_kinyarwanda",
            "image",
            "option_a_image", "option_b_image", "option_c_image", "option_d_image",
            "road_sign", "is_active",
        ]

    def validate_correct_option(self, value):
        if value.upper() not in ("A", "B", "C", "D"):
            raise serializers.ValidationError("Correct option must be A, B, C, or D.")
        return value.upper()


# ===========================================================================
# Quiz & QuizQuestionItem (Quiz Bank / Course Assessment Engine)
# ===========================================================================

class QuizQuestionItemSerializer(serializers.ModelSerializer):
    original_question = serializers.PrimaryKeyRelatedField(
        queryset=QuizQuestion.objects.all(),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = QuizQuestionItem
        fields = [
            "id", "sort_order", "original_question",
            "points", "question_text", "question_text_kinyarwanda",
            "option_a", "option_b", "option_c", "option_d",
            "option_a_kinyarwanda", "option_b_kinyarwanda", "option_c_kinyarwanda", "option_d_kinyarwanda",
            "correct_option", "explanation", "explanation_kinyarwanda",
            "domain", "difficulty",
        ]
        read_only_fields = ["id"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user and user.is_authenticated and user.role in (UserRole.STUDENT, UserRole.GUEST):
            data.pop("correct_option", None)
            data.pop("explanation", None)
            data.pop("explanation_kinyarwanda", None)
        return data


class QuizCreatorSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    phone_number = serializers.CharField(read_only=True)
    first_name = serializers.CharField(read_only=True)
    last_name = serializers.CharField(read_only=True)
    full_name = serializers.SerializerMethodField()
    username = serializers.SerializerMethodField()
    role = serializers.CharField(read_only=True)

    def get_full_name(self, obj):
        name = f"{getattr(obj, 'first_name', '')} {getattr(obj, 'last_name', '')}".strip()
        return name or getattr(obj, "phone_number", "") or "Admin"

    def get_username(self, obj):
        name = f"{getattr(obj, 'first_name', '')} {getattr(obj, 'last_name', '')}".strip()
        return name or getattr(obj, "phone_number", "") or "admin"


class QuizListSerializer(serializers.ModelSerializer):
    course_title = serializers.CharField(source="course.title", read_only=True)
    module_title = serializers.CharField(source="module.title", read_only=True, default=None)
    created_by_detail = QuizCreatorSerializer(source="created_by", read_only=True)
    created_by_name = serializers.SerializerMethodField()
    question_count = serializers.IntegerField(read_only=True)
    status = serializers.CharField(read_only=True)
    calculated_total_points = serializers.IntegerField(read_only=True)

    is_locked = serializers.SerializerMethodField()

    def get_is_locked(self, obj):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            if user.role == UserRole.TUTOR:
                tutor_cohorts = user.assigned_cohorts.filter(is_active=True)
                cohort_param = request.query_params.get("cohort") if request else None
                if cohort_param:
                    tutor_cohorts = tutor_cohorts.filter(id=cohort_param)
                if tutor_cohorts.exists():
                    sch = obj.cohort_schedules.filter(cohort__in=tutor_cohorts).first()
                    if sch:
                        return sch.is_locked or (not sch.is_published)
                    # By default, quiz is locked for tutor's cohort until tutor unlocks/publishes it
                    return True
                return True
            elif user.role in (UserRole.STUDENT, UserRole.GUEST):
                enrolled_cohorts = user.enrolled_cohorts.all()
                if not enrolled_cohorts.exists():
                    return True
                sch = obj.cohort_schedules.filter(cohort__in=enrolled_cohorts).first()
                if sch:
                    return sch.is_locked or (not sch.is_published)
                return True
        return False

    def get_created_by_name(self, obj):
        if obj.created_by:
            name = f"{obj.created_by.first_name} {obj.created_by.last_name}".strip()
            return name or obj.created_by.phone_number or "Admin"
        return "Training Admin"

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not data.get("created_by_detail"):
            creator = instance.created_by
            if creator:
                full_name = f"{creator.first_name} {creator.last_name}".strip() or creator.phone_number or "Admin"
                data["created_by_detail"] = {
                    "id": str(creator.id),
                    "phone_number": creator.phone_number,
                    "first_name": creator.first_name,
                    "last_name": creator.last_name,
                    "full_name": full_name,
                    "username": full_name,
                    "role": creator.role,
                }
            else:
                data["created_by_detail"] = {
                    "id": "admin-staff",
                    "phone_number": "+250788111222",
                    "first_name": "Eric",
                    "last_name": "Hategekimana",
                    "full_name": "Eric Hategekimana",
                    "username": "Eric Hategekimana",
                    "role": "TRAINING_ADMIN",
                }
        return data

    class Meta:
        model = Quiz
        fields = [
            "id", "course", "course_title", "module", "module_title",
            "quiz_type", "enable_proctoring", "max_tab_switches_allowed",
            "title", "title_kinyarwanda", "description", "description_kinyarwanda",
            "open_date", "deadline", "closing_date", "allow_late_submission", "is_final_exam",
            "time_limit_minutes", "total_score",
            "calculated_total_points", "passing_score", "max_attempts",
            "shuffle_questions", "is_published", "release_grades_immediately", "is_locked", "status", "question_count",
            "rubric", "rubric_kinyarwanda",
            "allow_tutor_scheduling", "allow_tutor_edit_instructions",
            "allow_tutor_edit_duration", "allow_tutor_edit_attempts",
            "created_by", "created_by_name", "created_by_detail", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "status", "question_count", "calculated_total_points", "is_locked", "created_at", "updated_at"]


class QuizDetailSerializer(QuizListSerializer):
    items = QuizQuestionItemSerializer(many=True, read_only=True)

    class Meta(QuizListSerializer.Meta):
        fields = QuizListSerializer.Meta.fields + [
            "items",
        ]


class QuizWriteSerializer(serializers.ModelSerializer):
    items = QuizQuestionItemSerializer(many=True, required=False)

    class Meta:
        model = Quiz
        fields = [
            "id", "course", "module", "quiz_type", "enable_proctoring", "max_tab_switches_allowed",
            "title", "title_kinyarwanda",
            "description", "description_kinyarwanda",
            "open_date", "deadline", "closing_date", "allow_late_submission", "is_final_exam",
            "time_limit_minutes", "total_score", "passing_score",
            "rubric", "rubric_kinyarwanda",
            "max_attempts", "shuffle_questions", "is_published", "release_grades_immediately",
            "allow_tutor_scheduling", "allow_tutor_edit_instructions",
            "allow_tutor_edit_duration", "allow_tutor_edit_attempts",
            "items",
        ]
        read_only_fields = ["id"]

    def validate(self, attrs):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        items = attrs.get("items", [])

        is_final = attrs.get("is_final_exam", getattr(self.instance, "is_final_exam", False))
        allow_late = attrs.get("allow_late_submission", getattr(self.instance, "allow_late_submission", False))

        # Final exam rule: late submission is strictly disallowed
        if is_final and allow_late:
            raise serializers.ValidationError({
                "allow_late_submission": "Final exams enforce strict deadline cutoff. Late submissions are not permitted."
            })

        # Closing date validation: cannot be before deadline
        deadline = attrs.get("deadline", getattr(self.instance, "deadline", None))
        closing_date = attrs.get("closing_date", getattr(self.instance, "closing_date", None))
        if deadline and closing_date and closing_date < deadline:
            raise serializers.ValidationError({
                "closing_date": "Closing date cannot be earlier than the standard deadline."
            })

        # System Admin restriction: cannot author from scratch
        if user and getattr(user, "role", None) == UserRole.SYSTEM_ADMIN:
            for idx, item in enumerate(items):
                if not item.get("original_question"):
                    raise serializers.ValidationError({
                        "items": (
                            f"System Admin may only build quizzes using items pulled from the Question Bank. "
                            f"Question #{idx + 1} ('{item.get('question_text', '')[:30]}...') is authored from scratch. "
                            f"Scratch authoring is reserved for Training Admin."
                        )
                    })

        # Calculate total_score from sum of question item points
        if items:
            attrs["total_score"] = sum(max(1, int(item.get("points", 1))) for item in items)
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        items_data = validated_data.pop("items", [])
        if items_data:
            validated_data["total_score"] = sum(max(1, int(item.get("points", 1))) for item in items_data)
        request = self.context.get("request")
        if "created_by" not in validated_data and request and request.user and request.user.is_authenticated:
            validated_data["created_by"] = request.user
        quiz = Quiz.objects.create(**validated_data)
        for idx, item_data in enumerate(items_data):
            sort_order = item_data.pop("sort_order", idx + 1)
            QuizQuestionItem.objects.create(quiz=quiz, sort_order=sort_order, **item_data)
        if items_data:
            total = quiz.items.aggregate(total=models.Sum("points"))["total"]
            if total is not None and total > 0:
                quiz.total_score = total
                quiz.save(update_fields=["total_score"])
        return quiz

    @transaction.atomic
    def update(self, instance, validated_data):
        items_data = validated_data.pop("items", None)
        if items_data is not None and len(items_data) > 0:
            validated_data["total_score"] = sum(max(1, int(item.get("points", 1))) for item in items_data)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if items_data is not None:
            instance.items.all().delete()
            for idx, item_data in enumerate(items_data):
                sort_order = item_data.pop("sort_order", idx + 1)
                QuizQuestionItem.objects.create(quiz=instance, sort_order=sort_order, **item_data)
            total = instance.items.aggregate(total=models.Sum("points"))["total"]
            if total is not None and total > 0:
                instance.total_score = total
                instance.save(update_fields=["total_score"])
        return instance


# ===========================================================================
# QuizSubmission (Student Live Attempt & Work Submission Lifecycle)
# ===========================================================================

class QuizSubmissionSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    student_phone = serializers.CharField(source="student.phone_number", read_only=True)
    cohort_name = serializers.CharField(source="cohort.name", read_only=True, default=None)
    quiz_title = serializers.CharField(source="quiz.title", read_only=True)
    work_submission_file_url = serializers.SerializerMethodField()
    question_breakdown = serializers.SerializerMethodField()
    graded_by_name = serializers.SerializerMethodField()
    grade_overridden_by_name = serializers.SerializerMethodField()
    is_grades_published = serializers.SerializerMethodField()

    def get_is_grades_published(self, obj):
        from django.utils import timezone
        now = timezone.now()
        quiz = getattr(obj, "quiz", None)
        cohort = getattr(obj, "cohort", None)
        sched = None
        if quiz and cohort:
            from apps.lms.models import CohortQuizSchedule
            sched = CohortQuizSchedule.objects.filter(cohort=cohort, quiz=quiz).first()

        effective_open = (sched and sched.open_date) or (quiz and quiz.open_date)
        effective_deadline = (sched and sched.deadline) or (quiz and quiz.deadline)

        # Cannot release or disclose grades to students before open date or deadline has passed
        if effective_open and effective_open > now:
            return False
        if effective_deadline and effective_deadline > now:
            return False

        if quiz and getattr(quiz, "release_grades_immediately", False):
            return True
        if sched and (getattr(sched, "release_grades_immediately", False) or getattr(sched, "grades_published", False)):
            return True
        elif quiz:
            from apps.lms.models import CohortQuizSchedule
            if CohortQuizSchedule.objects.filter(quiz=quiz, grades_published=True).exists():
                return True
        return False

    def get_graded_by_name(self, obj):
        if not obj.graded_by:
            return None
        name = obj.graded_by.get_full_name() if hasattr(obj.graded_by, "get_full_name") else ""
        return name or getattr(obj.graded_by, "phone_number", "") or "Staff"

    def get_grade_overridden_by_name(self, obj):
        user = obj.grade_overridden_by or (obj.graded_by if obj.is_grade_overridden else None)
        if not user:
            return None
        name = user.get_full_name() if hasattr(user, "get_full_name") else ""
        return name or getattr(user, "phone_number", "") or "Staff"

    def get_student_name(self, obj):
        name = f"{getattr(obj.student, 'first_name', '')} {getattr(obj.student, 'last_name', '')}".strip()
        return name or getattr(obj.student, "phone_number", "") or "Student"

    def get_work_submission_file_url(self, obj):
        if not obj.work_submission_file:
            return None
        request = self.context.get("request")
        if request:
            return request.build_absolute_uri(obj.work_submission_file.url)
        return getattr(obj.work_submission_file, "url", None)

    def get_question_breakdown(self, obj):
        """
        Provides detailed breakdown of questions, options, student's selected answer,
        and correctness for staff/tutors to review submitted contents.
        """
        student_answers = obj.student_answers or {}
        items = obj.quiz.items.all().order_by("sort_order")
        flagged_list = [str(x) for x in (getattr(obj, "flagged_questions", None) or [])]
        breakdown = []
        for it in items:
            it_key = str(it.id)
            selected = student_answers.get(it_key)
            if selected is None:
                selected = student_answers.get(str(it.sort_order))
            is_correct = False
            if selected is not None and it.correct_option:
                is_correct = str(selected).strip().upper() == str(it.correct_option).strip().upper()

            is_flagged_for_review = it_key in flagged_list or str(it.sort_order) in flagged_list

            options_dict = {}
            if it.option_a:
                options_dict["A"] = it.option_a
            if it.option_b:
                options_dict["B"] = it.option_b
            if it.option_c:
                options_dict["C"] = it.option_c
            if it.option_d:
                options_dict["D"] = it.option_d

            breakdown.append({
                "item_id": it_key,
                "order": it.sort_order,
                "question_text": it.question_text,
                "points": it.points,
                "options": options_dict,
                "correct_option": it.correct_option,
                "explanation": it.explanation,
                "student_answer": selected,
                "is_correct": is_correct,
                "is_flagged_for_review": is_flagged_for_review,
            })
        return breakdown

    class Meta:
        model = QuizSubmission
        fields = [
            "id", "quiz", "quiz_title", "student", "student_name", "student_phone",
            "cohort", "cohort_name", "attempt_number", "quiz_type",
            "score", "total_score", "percentage", "is_passed",
            "is_auto_graded", "auto_score", "is_grade_overridden",
            "grade_overridden_by", "grade_overridden_by_name", "grade_overridden_at", "grade_override_reason",
            "student_answers", "work_submission_text", "work_submission_file", "work_submission_file_url",
            "question_breakdown", "flagged_questions",
            "time_spent_seconds", "tab_switch_count", "proctoring_violations", "is_flagged",
            "is_grades_published",
            "feedback", "graded_by", "graded_by_name", "graded_at", "created_at",
        ]
        read_only_fields = [
            "id", "score", "total_score", "percentage", "is_passed",
            "is_flagged", "is_auto_graded", "auto_score", "is_grade_overridden",
            "grade_overridden_by", "grade_overridden_by_name", "grade_overridden_at",
            "is_grades_published",
            "graded_by", "graded_by_name", "graded_at", "created_at",
        ]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        user = getattr(request, "user", None)
        # Redact results for students if grades are not published or set to immediate release
        if user and getattr(user, "role", None) == UserRole.STUDENT:
            is_published = data.get("is_grades_published", False)
            if not is_published:
                data["score"] = None
                data["percentage"] = None
                data["is_passed"] = None
                data["auto_score"] = None
                data["question_breakdown"] = []
                data["feedback"] = ""
        return data

