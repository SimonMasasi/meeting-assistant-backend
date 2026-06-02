"""Integration tests for /auth endpoints."""
import pytest
from sqlmodel import Session, select
from fastapi.testclient import TestClient

from src.modules.auth.models import User, UserAuthToken
from src.shared.database import engine
from src.utils.passwords import PasswordManager
from src.utils.generators import Generator
from src.utils.jwt_auth import JWTAuth
from src.shared.enums import UserAuthTokensTypes
from datetime import datetime, timedelta

_pm = PasswordManager()
_jwt = JWTAuth()

REGISTER_URL = "/auth/register"
LOGIN_URL = "/auth/login"
REFRESH_URL = "/auth/refresh-token"
ME_URL = "/auth/me"
CHANGE_PW_URL = "/auth/change-password"
FORGOT_TOKEN_URL = "/auth/request-forgot-password-token"
FORGOT_PW_URL = "/auth/forgot-password"
USERS_URL = "/auth/users"

VALID_PASSWORD = "Test@1234"
WEAK_PASSWORD = "weakpass"


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------


class TestRegister:
    def test_register_success(self, client: TestClient):
        resp = client.post(
            REGISTER_URL,
            json={
                "username": "newuser",
                "email": "new@example.com",
                "password": VALID_PASSWORD,
            },
        )
        body = resp.json()
        assert resp.status_code == 200
        assert body["response"]["status"] is True
        assert body["data"]["username"] == "newuser"
        assert body["data"]["email"] == "new@example.com"
        # password must never be exposed
        assert "password" not in body["data"]

    def test_register_weak_password_fails(self, client: TestClient):
        resp = client.post(
            REGISTER_URL,
            json={
                "username": "newuser2",
                "email": "new2@example.com",
                "password": WEAK_PASSWORD,
            },
        )
        body = resp.json()
        assert body["response"]["status"] is False

    def test_register_duplicate_email_fails(self, client: TestClient, user: User):
        resp = client.post(
            REGISTER_URL,
            json={
                "username": "differentuser",
                "email": user.email,  # same email
                "password": VALID_PASSWORD,
            },
        )
        body = resp.json()
        assert body["response"]["status"] is False
        assert "Email" in body["response"]["message"] or "email" in body["response"]["message"]

    def test_register_duplicate_username_fails(self, client: TestClient, user: User):
        resp = client.post(
            REGISTER_URL,
            json={
                "username": user.username,  # same username
                "email": "unique@example.com",
                "password": VALID_PASSWORD,
            },
        )
        body = resp.json()
        assert body["response"]["status"] is False


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


class TestLogin:
    def test_login_success(self, client: TestClient, user: User):
        resp = client.post(
            LOGIN_URL,
            json={"username": user.username, "password": "Test@1234"},
        )
        body = resp.json()
        assert body["response"]["status"] is True
        assert "accessToken" in body["data"]
        assert "refreshToken" in body["data"]
        assert body["data"]["tokenType"] == "bearer"

    def test_login_wrong_password(self, client: TestClient, user: User):
        resp = client.post(
            LOGIN_URL,
            json={"username": user.username, "password": "WrongPass@1"},
        )
        body = resp.json()
        assert body["response"]["status"] is False

    def test_login_nonexistent_user(self, client: TestClient):
        resp = client.post(
            LOGIN_URL,
            json={"username": "ghost", "password": VALID_PASSWORD},
        )
        body = resp.json()
        assert body["response"]["status"] is False

    def test_account_lockout_after_five_failures(
        self, client: TestClient, user: User
    ):
        for _ in range(5):
            client.post(
                LOGIN_URL,
                json={"username": user.username, "password": "BadPass@1"},
            )
        # Account is locked – even the correct password must now fail
        resp = client.post(
            LOGIN_URL,
            json={"username": user.username, "password": "Test@1234"},
        )
        body = resp.json()
        assert body["response"]["status"] is False
        assert "locked" in body["response"]["message"].lower()


# ---------------------------------------------------------------------------
# Refresh token
# ---------------------------------------------------------------------------


class TestRefreshToken:
    def _get_refresh_token(self, client: TestClient, user: User) -> str:
        resp = client.post(
            LOGIN_URL, json={"username": user.username, "password": "Test@1234"}
        )
        return resp.json()["data"]["refreshToken"]

    def test_refresh_returns_new_access_token(self, client: TestClient, user: User):
        refresh_token = self._get_refresh_token(client, user)
        resp = client.post(REFRESH_URL, params={"refresh_token": refresh_token})
        body = resp.json()
        assert body["response"]["status"] is True
        assert "accessToken" in body["data"]

    def test_refresh_with_invalid_token_fails(self, client: TestClient):
        resp = client.post(REFRESH_URL, params={"refresh_token": "notavalidtoken"})
        body = resp.json()
        assert body["response"]["status"] is False

    def test_refresh_with_access_token_succeeds_due_to_no_type_check(self, client: TestClient, user: User):
        # The auth service's refresh endpoint decodes any valid JWT without
        # checking the token type, so an access token is accepted.  This test
        # documents that current (permissive) behaviour.
        resp = client.post(
            LOGIN_URL, json={"username": user.username, "password": "Test@1234"}
        )
        access_token = resp.json()["data"]["accessToken"]
        resp2 = client.post(REFRESH_URL, params={"refresh_token": access_token})
        body = resp2.json()
        assert body["response"]["status"] is True


# ---------------------------------------------------------------------------
# /me endpoint
# ---------------------------------------------------------------------------


class TestGetCurrentUser:
    def test_me_returns_current_user(self, auth_client: TestClient, user: User):
        resp = auth_client.get(ME_URL)
        body = resp.json()
        assert resp.status_code == 200
        assert body["response"]["status"] is True
        assert body["data"]["username"] == user.username
        assert body["data"]["email"] == user.email

    def test_me_without_auth_returns_403(self, client: TestClient):
        resp = client.get(ME_URL)
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# List users
# ---------------------------------------------------------------------------


class TestListUsers:
    def test_get_all_users_returns_list(self, client: TestClient, user: User):
        resp = client.get(USERS_URL)
        body = resp.json()
        assert resp.status_code == 200
        assert isinstance(body["data"], list)
        assert len(body["data"]) >= 1

    def test_filter_by_email(self, client: TestClient, user: User):
        resp = client.get(USERS_URL, params={"email": user.email})
        body = resp.json()
        assert len(body["data"]) == 1
        assert body["data"][0]["email"] == user.email

    def test_filter_by_nonexistent_email_returns_empty(self, client: TestClient):
        resp = client.get(USERS_URL, params={"email": "nobody@example.com"})
        body = resp.json()
        assert body["data"] == []


# ---------------------------------------------------------------------------
# Forgot password flow
# ---------------------------------------------------------------------------


class TestForgotPassword:
    def test_request_token_for_known_email_succeeds(
        self, client: TestClient, user: User
    ):
        resp = client.post(FORGOT_TOKEN_URL, json={"email": user.email})
        body = resp.json()
        assert resp.status_code == 200
        assert body["response"]["status"] is True

    def test_request_token_for_unknown_email_also_returns_success(
        self, client: TestClient
    ):
        # Anti-enumeration: same success message for unknown email
        resp = client.post(FORGOT_TOKEN_URL, json={"email": "ghost@example.com"})
        body = resp.json()
        assert resp.status_code == 200

    def test_reset_password_with_valid_token_succeeds(
        self, client: TestClient, user: User
    ):
        # Request a reset token
        client.post(FORGOT_TOKEN_URL, json={"email": user.email})

        # Fetch the stored token from the DB
        with Session(engine) as session:
            token_row = session.exec(
                select(UserAuthToken).where(
                    UserAuthToken.user_id == user.id,
                    UserAuthToken.token_type == UserAuthTokensTypes.FORGET_PASSWORD,
                )
            ).first()
        assert token_row is not None

        resp = client.post(
            FORGOT_PW_URL,
            json={
                "token": token_row.token,
                "newPassword": "NewPass@5678",
                "verifyNewPassword": "NewPass@5678",
            },
        )
        body = resp.json()
        assert body["response"]["status"] is True

    def test_reset_password_with_invalid_token_fails(self, client: TestClient):
        resp = client.post(
            FORGOT_PW_URL,
            json={
                "token": "invalid-token",
                "newPassword": "NewPass@5678",
                "verifyNewPassword": "NewPass@5678",
            },
        )
        body = resp.json()
        assert body["response"]["status"] is False

    def test_reset_password_with_weak_password_fails(
        self, client: TestClient, user: User
    ):
        # ForgotPasswordInputDTO enforces min_length=8 on new_password, so a
        # short password is rejected at the Pydantic validation layer (422)
        # before the service logic even runs.
        client.post(FORGOT_TOKEN_URL, json={"email": user.email})
        with Session(engine) as session:
            token_row = session.exec(
                select(UserAuthToken).where(UserAuthToken.user_id == user.id)
            ).first()

        resp = client.post(
            FORGOT_PW_URL,
            json={
                "token": token_row.token,
                "newPassword": "weak",
                "verifyNewPassword": "weak",
            },
        )
        assert resp.status_code == 422
