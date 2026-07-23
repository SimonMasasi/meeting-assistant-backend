"""Integration tests for the resumable (tus) upload endpoints."""
import base64
import hashlib
import os
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from config import SETTINGS
from src.modules.auth.models import User
from src.modules.uploads.models import TusUpload, UploadedFile
from src.modules.uploads.tus_views import cleanup_expired_tus_uploads
from src.shared.database import engine
from src.shared.dependencies import get_current_user

TUS_URL = "/uploads/tus"
TUS_VERSION = "1.0.0"
_FAKE_MIMETYPE = "audio/wav"
_FAKE_FILE_PATH = "uploads_media/audio/test.wav"

OFFSET_CT = {"Content-Type": "application/offset+octet-stream"}


@pytest.fixture(autouse=True)
def tus_dir(tmp_path, monkeypatch):
    """Keep tus scratch buffers inside the test's tmp dir."""
    directory = tmp_path / "tus"
    directory.mkdir()
    monkeypatch.setattr(SETTINGS, "TUS_UPLOAD_DIR", str(directory))
    return directory


def _storage_patch():
    """Mock the provider so no bytes actually reach disk-backed storage."""
    return patch(
        "src.utils.uploads.uploads_manager.UploadsManager.upload_stream",
        return_value=(True, "OK", _FAKE_FILE_PATH),
    )


def _metadata(filename: str = "meeting.wav", filetype: str = "audio/wav") -> str:
    name_b64 = base64.b64encode(filename.encode()).decode()
    type_b64 = base64.b64encode(filetype.encode()).decode()
    return f"filename {name_b64},filetype {type_b64}"


def _create(client: TestClient, size: int, filename: str = "meeting.wav"):
    return client.post(
        TUS_URL,
        headers={
            "Tus-Resumable": TUS_VERSION,
            "Upload-Length": str(size),
            "Upload-Metadata": _metadata(filename),
        },
    )


def _key_from_location(resp) -> str:
    return resp.headers["Location"].rsplit("/", 1)[-1]


# ---------------------------------------------------------------------------
# OPTIONS / creation
# ---------------------------------------------------------------------------


class TestTusDiscovery:
    def test_options_advertises_protocol(self, client: TestClient):
        resp = client.options(TUS_URL)
        assert resp.status_code == 204
        assert resp.headers["Tus-Version"] == TUS_VERSION
        assert resp.headers["Tus-Resumable"] == TUS_VERSION
        assert resp.headers["Tus-Max-Size"] == str(2 * 1024 * 1024 * 1024)
        assert "creation" in resp.headers["Tus-Extension"]

    def test_create_returns_location(self, auth_client: TestClient):
        resp = _create(auth_client, 1024)
        assert resp.status_code == 201
        assert resp.headers["Upload-Offset"] == "0"
        assert "/uploads/tus/" in resp.headers["Location"]

    def test_create_requires_auth(self, client: TestClient):
        resp = _create(client, 1024)
        assert resp.status_code in (401, 403)

    def test_create_rejects_oversized_length(self, auth_client: TestClient):
        resp = _create(auth_client, SETTINGS.TUS_MAX_UPLOAD_SIZE_BYTES + 1)
        assert resp.status_code == 413

    def test_create_requires_tus_version(self, auth_client: TestClient):
        resp = auth_client.post(
            TUS_URL,
            headers={"Upload-Length": "10", "Upload-Metadata": _metadata()},
        )
        assert resp.status_code == 412

    def test_create_requires_filename_metadata(self, auth_client: TestClient):
        resp = auth_client.post(
            TUS_URL,
            headers={"Tus-Resumable": TUS_VERSION, "Upload-Length": "10"},
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# PATCH / resume
# ---------------------------------------------------------------------------


class TestTusUploadFlow:
    def test_chunked_upload_creates_uploaded_file(self, auth_client: TestClient):
        content = b"a" * 512 + b"b" * 512
        created = _create(auth_client, len(content))
        key = _key_from_location(created)

        with _storage_patch():
            first = auth_client.patch(
                f"{TUS_URL}/{key}",
                headers={"Tus-Resumable": TUS_VERSION, "Upload-Offset": "0", **OFFSET_CT},
                content=content[:512],
            )
            assert first.status_code == 204
            assert first.headers["Upload-Offset"] == "512"

            second = auth_client.patch(
                f"{TUS_URL}/{key}",
                headers={"Tus-Resumable": TUS_VERSION, "Upload-Offset": "512", **OFFSET_CT},
                content=content[512:],
            )

        # The final chunk finalizes and returns the file metadata.
        assert second.status_code == 200
        assert second.headers["Upload-Offset"] == str(len(content))
        body = second.json()
        assert body["response"]["status"] is True
        assert body["data"]["filename"] == "meeting.wav"
        assert body["data"]["size"] == len(content)

        with Session(engine) as session:
            stored = session.exec(select(UploadedFile)).all()
        assert len(stored) == 1
        assert stored[0].file_hash == hashlib.sha256(content).hexdigest()

    def test_head_reports_partial_offset(self, auth_client: TestClient):
        content = b"x" * 1000
        key = _key_from_location(_create(auth_client, len(content)))

        auth_client.patch(
            f"{TUS_URL}/{key}",
            headers={"Tus-Resumable": TUS_VERSION, "Upload-Offset": "0", **OFFSET_CT},
            content=content[:400],
        )

        resp = auth_client.head(f"{TUS_URL}/{key}", headers={"Tus-Resumable": TUS_VERSION})
        assert resp.status_code == 204
        assert resp.headers["Upload-Offset"] == "400"
        assert resp.headers["Upload-Length"] == "1000"

    def test_offset_mismatch_returns_conflict(self, auth_client: TestClient):
        key = _key_from_location(_create(auth_client, 100))
        resp = auth_client.patch(
            f"{TUS_URL}/{key}",
            headers={"Tus-Resumable": TUS_VERSION, "Upload-Offset": "50", **OFFSET_CT},
            content=b"y" * 10,
        )
        assert resp.status_code == 409

    def test_chunk_past_declared_length_rejected(self, auth_client: TestClient):
        key = _key_from_location(_create(auth_client, 10))
        resp = auth_client.patch(
            f"{TUS_URL}/{key}",
            headers={"Tus-Resumable": TUS_VERSION, "Upload-Offset": "0", **OFFSET_CT},
            content=b"z" * 50,
        )
        assert resp.status_code == 413

    def test_wrong_content_type_rejected(self, auth_client: TestClient):
        key = _key_from_location(_create(auth_client, 10))
        resp = auth_client.patch(
            f"{TUS_URL}/{key}",
            headers={
                "Tus-Resumable": TUS_VERSION,
                "Upload-Offset": "0",
                "Content-Type": "application/octet-stream",
            },
            content=b"z" * 10,
        )
        assert resp.status_code == 415

    def test_duplicate_content_returns_existing_file(self, auth_client: TestClient):
        content = b"identical audio payload"

        with _storage_patch():
            for _ in range(2):
                key = _key_from_location(_create(auth_client, len(content)))
                resp = auth_client.patch(
                    f"{TUS_URL}/{key}",
                    headers={"Tus-Resumable": TUS_VERSION, "Upload-Offset": "0", **OFFSET_CT},
                    content=content,
                )

        assert resp.status_code == 200
        assert "already exists" in resp.json()["response"]["message"]
        with Session(engine) as session:
            assert len(session.exec(select(UploadedFile)).all()) == 1


# ---------------------------------------------------------------------------
# Ownership, termination, expiry
# ---------------------------------------------------------------------------


class TestTusOwnershipAndLifecycle:
    def test_other_user_cannot_resume(self, auth_client: TestClient, second_user: User):
        from app import app

        key = _key_from_location(_create(auth_client, 100))

        app.dependency_overrides[get_current_user] = lambda: second_user
        try:
            resp = auth_client.head(f"{TUS_URL}/{key}", headers={"Tus-Resumable": TUS_VERSION})
        finally:
            app.dependency_overrides.clear()

        assert resp.status_code == 403

    def test_delete_removes_upload_and_buffer(self, auth_client: TestClient):
        key = _key_from_location(_create(auth_client, 100))
        with Session(engine) as session:
            temp_path = session.exec(
                select(TusUpload).where(TusUpload.upload_key == key)
            ).first().temp_path
        assert os.path.exists(temp_path)

        resp = auth_client.delete(f"{TUS_URL}/{key}", headers={"Tus-Resumable": TUS_VERSION})

        assert resp.status_code == 204
        assert not os.path.exists(temp_path)
        with Session(engine) as session:
            assert session.exec(select(TusUpload).where(TusUpload.upload_key == key)).first() is None

    def test_unknown_key_returns_not_found(self, auth_client: TestClient):
        resp = auth_client.head(f"{TUS_URL}/nosuchkey", headers={"Tus-Resumable": TUS_VERSION})
        assert resp.status_code == 404

    def test_cleanup_reaps_expired_uploads(self, auth_client: TestClient):
        key = _key_from_location(_create(auth_client, 100))
        with Session(engine) as session:
            row = session.exec(select(TusUpload).where(TusUpload.upload_key == key)).first()
            temp_path = row.temp_path
            row.expires_at = datetime.now() - timedelta(seconds=1)
            session.add(row)
            session.commit()

        assert cleanup_expired_tus_uploads() == 1
        assert not os.path.exists(temp_path)
        with Session(engine) as session:
            assert session.exec(select(TusUpload).where(TusUpload.upload_key == key)).first() is None

    def test_expired_upload_rejects_patch(self, auth_client: TestClient):
        key = _key_from_location(_create(auth_client, 100))
        with Session(engine) as session:
            row = session.exec(select(TusUpload).where(TusUpload.upload_key == key)).first()
            row.expires_at = datetime.now() - timedelta(seconds=1)
            session.add(row)
            session.commit()

        resp = auth_client.patch(
            f"{TUS_URL}/{key}",
            headers={"Tus-Resumable": TUS_VERSION, "Upload-Offset": "0", **OFFSET_CT},
            content=b"z" * 10,
        )
        assert resp.status_code == 410
