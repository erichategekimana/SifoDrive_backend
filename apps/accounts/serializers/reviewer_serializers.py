from rest_framework import serializers
from apps.accounts.models import ReviewerProfile


class ReviewerProfileSerializer(serializers.ModelSerializer):
    """Serializer for Board Reviewer details."""

    class Meta:
        model = ReviewerProfile
        fields = [
            "id",
            "reviewer_code",
            "inspector_badge_number",
            "accreditation_authority",
            "total_reviews_completed",
            "total_certifications_approved",
            "total_violations_confirmed",
            "is_active_reviewer",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "reviewer_code",
            "total_reviews_completed",
            "total_certifications_approved",
            "total_violations_confirmed",
            "created_at",
            "updated_at",
        ]


class ReviewerStatsSerializer(serializers.Serializer):
    """Response serializer for Board Reviewer dashboard stats."""

    reviewer_code = serializers.CharField()
    inspector_badge_number = serializers.CharField()
    accreditation_authority = serializers.CharField()
    total_reviews_completed = serializers.IntegerField()
    total_certifications_approved = serializers.IntegerField()
    total_violations_confirmed = serializers.IntegerField()
    pending_queue_count = serializers.IntegerField()
    is_active = serializers.BooleanField()


class ReviewerQueueItemSerializer(serializers.Serializer):
    """Serializer for an exam session flagged for proctoring audit."""

    session_id = serializers.CharField()
    candidate_name = serializers.CharField()
    candidate_phone = serializers.CharField()
    student_id = serializers.CharField(allow_null=True)
    exam_title = serializers.CharField()
    score_percentage = serializers.FloatField()
    flagged_reason = serializers.CharField()
    created_at = serializers.CharField(allow_null=True)


class ReviewerCertifyActionSerializer(serializers.Serializer):
    """Payload for certifying or rejecting a flagged exam session."""

    session_id = serializers.CharField()
    action = serializers.ChoiceField(choices=["APPROVE", "DISQUALIFY"])
    remarks = serializers.CharField(required=False, allow_blank=True, default="")
