import pytest
from rest_framework import status
from rest_framework.test import APIClient
from apps.accounts.constants import UserRole
from apps.accounts.models import User
from apps.lms.models import Curriculum, Course, Quiz, QuizQuestionItem, QuizSubmission, QuizType

@pytest.fixture
def api_client():
    return APIClient()

@pytest.fixture
def student_user(db):
    return User.objects.create_user(
        phone_number="+250788100001",
        password="TestPassword123!",
        role=UserRole.STUDENT,
        first_name="Jean",
        last_name="Mugisha",
    )

@pytest.fixture
def tutor_user(db):
    return User.objects.create_user(
        phone_number="+250788100002",
        password="TestPassword123!",
        role=UserRole.TUTOR,
        first_name="Paul",
        last_name="Kagabo",
    )

@pytest.fixture
def test_course(db):
    curriculum = Curriculum.objects.create(title="Rwanda Highway Code 2026", code="RW-CURR-TEST")
    return Course.objects.create(
        curriculum=curriculum,
        title="Category B Road Rules",
        code="CAT-B-01",
    )

@pytest.fixture
def live_quiz(db, test_course, tutor_user):
    quiz = Quiz.objects.create(
        course=test_course,
        title="Speed Limits & Priority Live Quiz",
        quiz_type=QuizType.LIVE_TIMED,
        enable_proctoring=True,
        max_tab_switches_allowed=2,
        time_limit_minutes=15,
        total_score=10,
        passing_score=70,
        max_attempts=1,
        is_published=True,
        created_by=tutor_user,
    )
    # Question 1 (5 pts, correct: A)
    QuizQuestionItem.objects.create(
        quiz=quiz,
        sort_order=1,
        points=5,
        question_text="What is the standard urban speed limit in Kigali?",
        option_a="40 km/h",
        option_b="60 km/h",
        correct_option="A",
    )
    # Question 2 (5 pts, correct: B)
    QuizQuestionItem.objects.create(
        quiz=quiz,
        sort_order=2,
        points=5,
        question_text="Who has priority at a roundabout?",
        option_a="Vehicles entering",
        option_b="Vehicles already inside",
        correct_option="B",
    )
    return quiz

@pytest.fixture
def work_submission_quiz(db, test_course, tutor_user):
    return Quiz.objects.create(
        course=test_course,
        title="Road Safety Risk Assessment Work Assignment",
        quiz_type=QuizType.WORK_SUBMISSION,
        enable_proctoring=False,
        time_limit_minutes=0,
        total_score=100,
        passing_score=60,
        max_attempts=2,
        is_published=True,
        created_by=tutor_user,
    )

@pytest.mark.django_db
def test_student_live_quiz_submission_with_proctoring(api_client, student_user, live_quiz):
    api_client.force_authenticate(user=student_user)
    items = list(live_quiz.items.all())
    item_1 = items[0]
    item_2 = items[1]

    # Student answers Q1 correctly ('A'), Q2 incorrectly ('A')
    # Proctoring: 3 tab switches (threshold is 2) -> should be flagged
    payload = {
        "student_answers": {
            str(item_1.id): "A",
            str(item_2.id): "A",
        },
        "time_spent_seconds": 320,
        "tab_switch_count": 3,
        "proctoring_violations": [
            {"timestamp": "2026-10-09T18:00:00Z", "event": "tab_switch"},
            {"timestamp": "2026-10-09T18:02:10Z", "event": "tab_switch"},
            {"timestamp": "2026-10-09T18:04:05Z", "event": "tab_switch"},
        ],
    }

    url = f"/api/v1/lms/quizzes/{live_quiz.id}/submit/"
    response = api_client.post(url, data=payload, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    data = response.data["data"]
    assert data["score"] == 5
    assert data["total_score"] == 10
    assert data["percentage"] == 50.0
    assert data["is_passed"] is False
    assert data["tab_switch_count"] == 3
    assert data["is_flagged"] is True
    assert data["attempt_number"] == 1

    # Second attempt should be blocked because max_attempts = 1
    second_response = api_client.post(url, data=payload, format="json")
    assert second_response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_student_work_submission_quiz(api_client, student_user, work_submission_quiz):
    api_client.force_authenticate(user=student_user)

    payload = {
        "work_submission_text": "Here is my detailed analysis on night-time visibility and braking distances.",
        "time_spent_seconds": 1200,
        "tab_switch_count": 0,
    }

    url = f"/api/v1/lms/quizzes/{work_submission_quiz.id}/submit/"
    response = api_client.post(url, data=payload, format="json")

    assert response.status_code == status.HTTP_201_CREATED
    data = response.data["data"]
    assert data["quiz_type"] == QuizType.WORK_SUBMISSION
    assert data["work_submission_text"] == payload["work_submission_text"]
    assert data["is_flagged"] is False
    assert data["attempt_number"] == 1


@pytest.mark.django_db
def test_submissions_list_filtering(api_client, tutor_user, student_user, live_quiz):
    # Create submission
    QuizSubmission.objects.create(
        quiz=live_quiz,
        student=student_user,
        attempt_number=1,
        quiz_type=live_quiz.quiz_type,
        score=10,
        total_score=10,
        percentage=100.0,
        is_passed=True,
        tab_switch_count=4,
        is_flagged=True,
    )

    # Tutor accesses submissions list
    api_client.force_authenticate(user=tutor_user)
    url = f"/api/v1/lms/quizzes/{live_quiz.id}/submissions/?is_flagged=true"
    response = api_client.get(url)

    assert response.status_code == status.HTTP_200_OK
    assert len(response.data["results"]) == 1
    assert response.data["results"][0]["is_flagged"] is True
    assert response.data["results"][0]["student_phone"] == student_user.phone_number
