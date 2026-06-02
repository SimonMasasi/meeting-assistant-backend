import pytest
import jwt as pyjwt
from datetime import datetime, timezone, timedelta

from src.utils.jwt_auth import JWTAuth
from src.modules.auth.models import User
from src.utils.generators import Generator

# Use an isolated secret so tests don't depend on SETTINGS
_jwt = JWTAuth(secret_key="unit-test-secret", algorithm="HS256")

TEST_USER_ID = Generator.generate_64bit_int_uuid()


def _make_user(**overrides) -> User:
    defaults = {
        "id": TEST_USER_ID,
        "username": "testuser",
        "email": "test@example.com",
        "password": "hashed",
    }
    defaults.update(overrides)
    return User(**defaults)


class TestEncodeAndDecode:
    def test_roundtrip(self):
        payload = {
            "type": "access",
            "user_id": 42,
            "exp": (datetime.now(tz=timezone.utc) + timedelta(minutes=5)).timestamp(),
        }
        token = _jwt.encode(payload)
        decoded = _jwt.decode(token)
        assert decoded["user_id"] == 42
        assert decoded["type"] == "access"

    def test_expired_token_raises(self):
        payload = {
            "user_id": 1,
            "type": "access",
            "exp": (datetime.now(tz=timezone.utc) - timedelta(seconds=1)).timestamp(),
        }
        token = pyjwt.encode(payload, "unit-test-secret", algorithm="HS256")
        with pytest.raises(ValueError, match="expired"):
            _jwt.decode(token)

    def test_invalid_token_raises(self):
        with pytest.raises(ValueError, match="Invalid token"):
            _jwt.decode("this.is.not.a.valid.token")

    def test_wrong_signature_raises(self):
        payload = {
            "user_id": 1,
            "type": "access",
            "exp": (datetime.now(tz=timezone.utc) + timedelta(minutes=5)).timestamp(),
        }
        token = pyjwt.encode(payload, "different-secret", algorithm="HS256")
        with pytest.raises(ValueError, match="Invalid token"):
            _jwt.decode(token)


class TestCreateTokens:
    def test_access_and_refresh_are_different(self):
        user = _make_user()
        access, refresh, expires_in = _jwt.create_access_token_and_refresh_token(user)
        assert access != refresh
        assert isinstance(expires_in, int)

    def test_access_token_type(self):
        user = _make_user()
        access, _, _ = _jwt.create_access_token_and_refresh_token(user)
        decoded = _jwt.decode(access)
        assert decoded["type"] == "access"
        assert decoded["user_id"] == user.id
        assert decoded["username"] == user.username

    def test_refresh_token_type(self):
        user = _make_user()
        _, refresh, _ = _jwt.create_access_token_and_refresh_token(user)
        decoded = _jwt.decode(refresh)
        assert decoded["type"] == "refresh"

    def test_password_reset_token_type(self):
        user = _make_user()
        token = _jwt.create_password_reset_token(user)
        decoded = _jwt.decode(token)
        assert decoded["type"] == "password_reset"
        assert decoded["user_id"] == user.id


class TestRefreshAccessToken:
    def test_refresh_produces_new_access_token(self):
        user = _make_user()
        _, refresh, _ = _jwt.create_access_token_and_refresh_token(user)
        new_access, expires_in = _jwt.refresh_access_token(refresh)
        decoded = _jwt.decode(new_access)
        assert decoded["type"] == "access"
        assert isinstance(expires_in, int)

    def test_passing_access_token_as_refresh_raises(self):
        user = _make_user()
        access, _, _ = _jwt.create_access_token_and_refresh_token(user)
        with pytest.raises(ValueError, match="Invalid token type"):
            _jwt.refresh_access_token(access)
