import pytest
from rest_framework import status
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()

@pytest.mark.django_db
class TestAccountFeatures:
    def test_update_profile_fields(self, client):
        user = User.objects.create_user(
            phone_number="+250788111222",
            password="OldPassword123!",
            first_name="Jean",
            last_name="Claude"
        )
        refresh = RefreshToken.for_user(user)
        token = str(refresh.access_token)

        patch_data = {
            "first_name": "Jean Baptiste",
            "last_name": "Mugisha",
            "biography": "Aspiring commercial driver aiming for Category B.",
            "links": [{"title": "LinkedIn", "url": "https://linkedin.com/in/jbmugisha"}],
            "contact_methods": [{"type": "email", "value": "jb@example.com"}],
            "two_factor_enabled": True,
            "two_factor_method": "phone"
        }

        response = client.patch(
            "/api/v1/auth/me/",
            data=patch_data,
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}"
        )

        assert response.status_code == status.HTTP_200_OK
        res_json = response.json()
        data = res_json.get("data", res_json)
        assert data["first_name"] == "Jean Baptiste"
        assert data["last_name"] == "Mugisha"
        assert data["biography"] == "Aspiring commercial driver aiming for Category B."
        assert len(data["links"]) == 1
        assert len(data["contact_methods"]) == 1
        assert data["two_factor_enabled"] is True
        assert data["two_factor_method"] == "phone"

    def test_change_password(self, client):
        user = User.objects.create_user(
            phone_number="+250788333444",
            password="CurrentPassword123!",
            first_name="Alice",
            last_name="Uwase"
        )
        refresh = RefreshToken.for_user(user)
        token = str(refresh.access_token)

        # 1. Invalid current password
        bad_response = client.post(
            "/api/v1/auth/password/change/",
            data={"current_password": "WrongPassword", "new_password": "NewSecretPassword123!"},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}"
        )
        assert bad_response.status_code == status.HTTP_400_BAD_REQUEST

        # 2. Valid current password
        good_response = client.post(
            "/api/v1/auth/password/change/",
            data={"current_password": "CurrentPassword123!", "new_password": "NewSecretPassword123!"},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}"
        )
        assert good_response.status_code == status.HTTP_200_OK

        # 3. Verify user can authenticate with new password
        user.refresh_from_db()
        assert user.check_password("NewSecretPassword123!") is True

    def test_active_sessions_and_terminate(self, client):
        user = User.objects.create_user(
            phone_number="+250788555666",
            password="Password123!",
            first_name="Eric",
            last_name="Manzi",
            last_login_ip="197.243.22.10"
        )
        refresh = RefreshToken.for_user(user)
        token = str(refresh.access_token)

        # GET sessions
        response = client.get(
            "/api/v1/auth/sessions/",
            HTTP_AUTHORIZATION=f"Bearer {token}",
            HTTP_USER_AGENT="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
        )
        assert response.status_code == status.HTTP_200_OK
        res_json = response.json()
        sessions = res_json.get("data", res_json)
        assert len(sessions) >= 1
        assert sessions[0]["ip_address"] == "197.243.22.10"

        # POST terminate
        term_response = client.post(
            "/api/v1/auth/sessions/terminate/",
            data={},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}"
        )
        assert term_response.status_code == status.HTTP_200_OK
