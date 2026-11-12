import pytest
from rest_framework import status
from accounts.factories import UserFactory
from accounts.models import User


def test_obtain_token_happy_path(api_client):
    user = UserFactory(username="client_1", role=User.Role.INGESTION_CLIENT)
    response = api_client.post(
        "/api/auth/token/",
        {"username": "client_1", "password": "defaultpassword123"},
        format="json",
    )
    assert response.status_code == status.HTTP_200_OK
    assert "access" in response.data
    assert "refresh" in response.data
    assert response.data["user"]["role"] == User.Role.INGESTION_CLIENT
    assert response.data["user"]["username"] == "client_1"


def test_obtain_token_invalid_credentials(api_client):
    UserFactory(username="client_2")
    response = api_client.post(
        "/api/auth/token/",
        {"username": "client_2", "password": "wrongpassword"},
        format="json",
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_refresh_token(api_client):
    UserFactory(username="client_3")
    token_resp = api_client.post(
        "/api/auth/token/",
        {"username": "client_3", "password": "defaultpassword123"},
        format="json",
    )
    refresh_token = token_resp.data["refresh"]

    refresh_resp = api_client.post(
        "/api/auth/token/refresh/",
        {"refresh": refresh_token},
        format="json",
    )
    assert refresh_resp.status_code == status.HTTP_200_OK
    assert "access" in refresh_resp.data


def test_current_user_authenticated(api_client, ingestion_client_user):
    api_client.force_authenticate(user=ingestion_client_user)
    response = api_client.get("/api/auth/me/")
    assert response.status_code == status.HTTP_200_OK
    assert response.data["username"] == ingestion_client_user.username
    assert response.data["role"] == User.Role.INGESTION_CLIENT


def test_current_user_unauthenticated(api_client):
    response = api_client.get("/api/auth/me/")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
