"""Integration tests for /settings endpoints."""
import pytest
from fastapi.testclient import TestClient

EMAIL_CONFIG_URL = "/settings/email-configuration"

VALID_CONFIG = {
    "smtpServer": "smtp.example.com",
    "smtpPort": 587,
    "username": "user@example.com",
    "password": "secretpassword",
    "senderEmail": "noreply@example.com",
}


class TestEmailConfiguration:
    def test_create_config_succeeds(self, client: TestClient):
        resp = client.post(EMAIL_CONFIG_URL, json=VALID_CONFIG)
        body = resp.json()
        assert resp.status_code == 200
        assert body["response"]["status"] is True
        assert body["data"]["smtpServer"] == "smtp.example.com"
        assert body["data"]["smtpPort"] == 587

    def test_password_is_not_exposed_in_response(self, client: TestClient):
        resp = client.post(EMAIL_CONFIG_URL, json=VALID_CONFIG)
        body = resp.json()
        # The password field has exclude=True on the model
        assert "password" not in body["data"]

    def test_second_post_updates_existing_config(self, client: TestClient):
        client.post(EMAIL_CONFIG_URL, json=VALID_CONFIG)

        updated = VALID_CONFIG.copy()
        updated["smtpServer"] = "smtp.updated.com"
        updated["smtpPort"] = 465

        resp = client.post(EMAIL_CONFIG_URL, json=updated)
        body = resp.json()
        assert body["response"]["status"] is True
        assert body["data"]["smtpServer"] == "smtp.updated.com"
        assert body["data"]["smtpPort"] == 465

    def test_get_config_when_none_exists_returns_failure(self, client: TestClient):
        resp = client.get(EMAIL_CONFIG_URL)
        body = resp.json()
        assert resp.status_code == 200
        assert body["response"]["status"] is False
        assert body["data"] is None

    def test_get_config_after_creation(self, client: TestClient):
        client.post(EMAIL_CONFIG_URL, json=VALID_CONFIG)
        resp = client.get(EMAIL_CONFIG_URL)
        body = resp.json()
        assert body["response"]["status"] is True
        assert body["data"]["smtpServer"] == "smtp.example.com"

    def test_create_config_invalid_port_fails(self, client: TestClient):
        bad = VALID_CONFIG.copy()
        bad["smtpPort"] = -1  # must be > 0
        resp = client.post(EMAIL_CONFIG_URL, json=bad)
        assert resp.status_code == 422

    def test_create_config_invalid_sender_email_fails(self, client: TestClient):
        bad = VALID_CONFIG.copy()
        bad["senderEmail"] = "not-an-email"
        resp = client.post(EMAIL_CONFIG_URL, json=bad)
        assert resp.status_code == 422
