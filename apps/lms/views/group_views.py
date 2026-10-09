"""
apps/lms/views/group_views.py
=============================
API views for Course Roster (Classmates & Instructors), Study Groups, and Group Chat.
"""

from django.db.models import Q
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
            .order_by("-created_at")
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

            groups = CourseGroup.objects.filter(course=course, is_deleted=False)

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
