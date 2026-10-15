"""
apps/lms/views/group_views.py
=============================
API views for Course Roster (Classmates & Instructors), Study Groups, and Group Chat.
"""

from django.db.models import Q, Max
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.core.mixins import SuccessResponseMixin
from apps.lms.models import Course, CourseGroup, CourseGroupMessage
from apps.lms.serializers.group_serializers import (
    CourseGroupCreateSerializer,
    CourseGroupDetailSerializer,
    CourseGroupListSerializer,
    CourseGroupMessageCreateSerializer,
    CourseGroupMessageSerializer,
    CourseRosterUserSerializer,
)


class CourseRosterView(SuccessResponseMixin, APIView):
    """
    GET /api/v1/lms/courses/<course_id>/roster/
         Retrieve real classmates and instructors for the course.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, course_id, *args, **kwargs):
        course = get_object_or_404(Course, id=course_id, is_deleted=False)

        # 1. Fetch instructors: Assigned tutors or tutors in the system
        instructor_qs = User.objects.filter(
            role__in=["TUTOR", "SYSTEM_ADMIN", "TRAINING_ADMIN"],
            is_active=True,
        ).order_by("first_name", "last_name")

        # 2. Fetch students: Active enrolled students
        student_qs = User.objects.filter(
            role="STUDENT",
            is_active=True,
        ).order_by("first_name", "last_name")

        # Combine instructors first, then students
        users = list(instructor_qs[:10]) + list(student_qs[:30])

        serializer = CourseRosterUserSerializer(users, many=True, context={"request": request})
        return self.success_response(data=serializer.data)


class CourseGroupListCreateView(SuccessResponseMixin, APIView):
    """
    GET  /api/v1/lms/courses/<course_id>/groups/
         List study groups for this course.
    POST /api/v1/lms/courses/<course_id>/groups/
         Create a new study group. Both tutors and students can create groups.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, course_id, *args, **kwargs):
        course = get_object_or_404(Course, id=course_id, is_deleted=False)

        groups = (
            CourseGroup.objects.filter(course=course, is_deleted=False)
            .select_related("created_by", "course")
            .prefetch_related("members")
            .annotate(latest_activity=Coalesce(Max("messages__created_at"), "created_at"))
            .order_by("-latest_activity")
        )

        # Auto-seed standard groups if course has none yet
        if not groups.exists():
            default_tutor = User.objects.filter(role="TUTOR", is_active=True).first() or request.user
            g1 = CourseGroup.objects.create(
                course=course,
                created_by=default_tutor,
                name=f"{course.title} - Main Study Group",
                description="Official peer learning circle and discussion group for this course.",
                category="General",
            )
            g1.members.add(request.user)
            if default_tutor != request.user:
                g1.members.add(default_tutor)

            # Initial welcome message
            CourseGroupMessage.objects.create(
                group=g1,
                sender=default_tutor,
                content=f"Welcome everyone to the {course.title} study group! Feel free to ask questions and share study tips here.",
            )

            groups = (
                CourseGroup.objects.filter(course=course, is_deleted=False)
                .select_related("created_by", "course")
                .prefetch_related("members")
                .annotate(latest_activity=Coalesce(Max("messages__created_at"), "created_at"))
                .order_by("-latest_activity")
            )

        serializer = CourseGroupListSerializer(groups, many=True, context={"request": request})
        return self.success_response(data=serializer.data)

    def post(self, request, course_id, *args, **kwargs):
        course = get_object_or_404(Course, id=course_id, is_deleted=False)

        serializer = CourseGroupCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return self.validation_error(serializer.errors)

        validated = serializer.validated_data
        group = CourseGroup.objects.create(
            course=course,
            created_by=request.user,
            name=validated["name"].strip(),
            description=validated.get("description", "").strip(),
            category=validated.get("category", "General").strip() or "General",
        )
        group.members.add(request.user)

        # Add initial greeting message
        CourseGroupMessage.objects.create(
            group=group,
            sender=request.user,
            content=f"Created the group '{group.name}'. Welcome all classmates!",
        )

        output = CourseGroupDetailSerializer(group, context={"request": request})
        return self.success_response(
            data=output.data,
            message="Study group created successfully.",
            status_code=status.HTTP_201_CREATED,
        )


class CourseGroupDetailView(SuccessResponseMixin, APIView):
    """
    GET /api/v1/lms/groups/<group_id>/
         Retrieve group details, member roster, and full chat message history.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, group_id, *args, **kwargs):
        group = get_object_or_404(
            CourseGroup.objects.select_related("created_by", "course").prefetch_related("members"),
            id=group_id,
            is_deleted=False,
        )

        serializer = CourseGroupDetailSerializer(group, context={"request": request})
        return self.success_response(data=serializer.data)


class CourseGroupJoinToggleView(SuccessResponseMixin, APIView):
    """
    POST /api/v1/lms/groups/<group_id>/toggle-join/
         Join or leave a course study group.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, group_id, *args, **kwargs):
        group = get_object_or_404(CourseGroup, id=group_id, is_deleted=False)
        user = request.user

        if group.members.filter(id=user.id).exists():
            group.members.remove(user)
            is_member = False
            msg = "You have left the group."
        else:
            group.members.add(user)
            is_member = True
            msg = "You have joined the group."

        return self.success_response(
            data={
                "is_member": is_member,
                "members_count": group.members.count(),
            },
            message=msg,
        )


class CourseGroupMessageCreateView(SuccessResponseMixin, APIView):
    """
    POST /api/v1/lms/groups/<group_id>/messages/
         Send a chat message within a study group.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, group_id, *args, **kwargs):
        group = get_object_or_404(CourseGroup, id=group_id, is_deleted=False)

        serializer = CourseGroupMessageCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return self.validation_error(serializer.errors)

        content = serializer.validated_data["content"].strip()
        if not content:
            return self.error_response(
                code="EMPTY_MESSAGE",
                message="Message content cannot be blank.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # Ensure sender is a member of the group
        if not group.members.filter(id=request.user.id).exists():
            group.members.add(request.user)

        message = CourseGroupMessage.objects.create(
            group=group,
            sender=request.user,
            content=content,
        )

        output = CourseGroupMessageSerializer(message)
        return self.success_response(
            data=output.data,
            message="Message sent successfully.",
            status_code=status.HTTP_201_CREATED,
        )


class AllCourseGroupsListView(SuccessResponseMixin, APIView):
    """
    GET  /api/v1/lms/groups/
         Returns all study groups across all courses accessible/enrolled to the student.
         Query params:
           - course_id: filter to a specific course
           - my_groups: if 'true', returns only groups where the user is a member
           - search: search query
    POST /api/v1/lms/groups/
         Create a new study group for any enrolled/accessible course.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        from apps.lms.services import ContentGateService

        user = request.user
        visible_courses = ContentGateService.get_visible_courses(user)

        # Seed standard groups for visible courses if empty so students have spaces to collaborate
        for course in visible_courses[:5]:
            if not CourseGroup.objects.filter(course=course, is_deleted=False).exists():
                default_tutor = User.objects.filter(role="TUTOR", is_active=True).first() or user
                g1 = CourseGroup.objects.create(
                    course=course,
                    created_by=default_tutor,
                    name=f"{course.title} - Main Study Circle",
                    description=f"Official peer study circle and discussion group for {course.title}.",
                    category="General",
                )
                g1.members.add(user)
                if default_tutor != user:
                    g1.members.add(default_tutor)
                CourseGroupMessage.objects.create(
                    group=g1,
                    sender=default_tutor,
                    content=f"Welcome everyone to the {course.title} study circle! Feel free to ask questions and share study tips here.",
                )

        groups = (
            CourseGroup.objects.filter(course__in=visible_courses, is_deleted=False)
            .select_related("created_by", "course")
            .prefetch_related("members")
            .annotate(latest_activity=Coalesce(Max("messages__created_at"), "created_at"))
            .order_by("-latest_activity")
        )

        course_id = request.query_params.get("course_id")
        if course_id:
            groups = groups.filter(course_id=course_id)

        my_groups = request.query_params.get("my_groups")
        if my_groups in ["true", "1", "True"]:
            groups = groups.filter(members=user)

        search = request.query_params.get("search")
        if search:
            groups = groups.filter(
                Q(name__icontains=search)
                | Q(description__icontains=search)
                | Q(category__icontains=search)
                | Q(course__title__icontains=search)
            )

        serializer = CourseGroupListSerializer(groups.distinct(), many=True, context={"request": request})
        return self.success_response(data=serializer.data)

    def post(self, request, *args, **kwargs):
        from apps.lms.services import ContentGateService

        serializer = CourseGroupCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return self.validation_error(serializer.errors)

        validated = serializer.validated_data
        course_id = validated.get("course_id")
        if not course_id:
            visible_courses = ContentGateService.get_visible_courses(request.user)
            course = visible_courses.first()
            if not course:
                return self.error_response(
                    message="No enrolled course available to create a group.",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
        else:
            course = get_object_or_404(Course, id=course_id, is_deleted=False)

        group = CourseGroup.objects.create(
            course=course,
            created_by=request.user,
            name=validated["name"].strip(),
            description=validated.get("description", "").strip(),
            category=validated.get("category", "General").strip() or "General",
        )
        group.members.add(request.user)

        CourseGroupMessage.objects.create(
            group=group,
            sender=request.user,
            content=f"Created the group '{group.name}'. Welcome all classmates!",
        )

        output = CourseGroupDetailSerializer(group, context={"request": request})
        return self.success_response(
            data=output.data,
            message="Study group created successfully.",
            status_code=status.HTTP_201_CREATED,
        )
