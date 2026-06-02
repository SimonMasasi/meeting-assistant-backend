"""Integration tests for /uploads endpoints."""
import io
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from src.modules.auth.models import User
from src.modules.uploads.models import UploadedFile
from src.shared.database import engine
from src.utils.generators import Generator
from sqlmodel import Session

UPLOAD_URL = "/uploads/upload-file"
GET_FILE_URL = "/uploads/get-file/{file_id}"

# Fake values returned by mocked provider calls
_FAKE_MIMETYPE = "image/jpeg"
_FAKE_FILE_PATH = "uploads_media/images/test.jpg"


def _persisted_file(db_session: Session) -> UploadedFile:
    """Insert an UploadedFile row directly and return it."""
    from src.shared.enums import FileTypeEnum

    f = UploadedFile(
        id=Generator.generate_64bit_int_uuid(),
        filename="existing.jpg",
        content_type="image/jpeg",
        size=512,
        file_path=_FAKE_FILE_PATH,
        file_type=FileTypeEnum.IMAGE,
        file_hash="uniquehash_existing",
        mimetype=_FAKE_MIMETYPE,
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)
    return f


def _upload_patch():
    """Context-manager that mocks all external I/O in the upload pipeline."""
    return (
        patch(
            "src.utils.uploads.uploads_manager.UploadsManager.get_file_mimetype",
            return_value=_FAKE_MIMETYPE,
        ),
        patch(
            "src.utils.uploads.uploads_manager.UploadsManager.upload_file",
            return_value=(True, "OK", _FAKE_FILE_PATH),
        ),
    )


# ---------------------------------------------------------------------------
# POST /uploads/upload-file
# ---------------------------------------------------------------------------


class TestUploadFile:
    def test_upload_image_succeeds(self, auth_client: TestClient):
        file_content = b"fake image bytes"
        with (
            patch(
                "src.utils.uploads.uploads_manager.UploadsManager.get_file_mimetype",
                return_value=_FAKE_MIMETYPE,
            ),
            patch(
                "src.utils.uploads.uploads_manager.UploadsManager.upload_file",
                return_value=(True, "OK", _FAKE_FILE_PATH),
            ),
        ):
            resp = auth_client.post(
                UPLOAD_URL,
                files={"file": ("photo.jpg", io.BytesIO(file_content), "image/jpeg")},
            )

        body = resp.json()
        assert resp.status_code == 200
        assert body["response"]["status"] is True
        assert body["data"]["filename"] == "photo.jpg"

    def test_upload_requires_auth(self, client: TestClient):
        resp = client.post(
            UPLOAD_URL,
            files={"file": ("photo.jpg", io.BytesIO(b"data"), "image/jpeg")},
        )
        assert resp.status_code in (401, 403)

    def test_upload_oversized_file_rejected(self, auth_client: TestClient):
        large_bytes = b"x" * (20 * 1024 * 1024 + 1)  # 20 MB + 1 byte
        with (
            patch(
                "src.utils.uploads.uploads_manager.UploadsManager.get_file_mimetype",
                return_value=_FAKE_MIMETYPE,
            ),
            patch(
                "src.utils.uploads.uploads_manager.UploadsManager.upload_file",
                return_value=(True, "OK", _FAKE_FILE_PATH),
            ),
        ):
            resp = auth_client.post(
                UPLOAD_URL,
                files={"file": ("big.jpg", io.BytesIO(large_bytes), "image/jpeg")},
            )
        body = resp.json()
        assert body["response"]["status"] is False
        assert "20MB" in body["response"]["message"]

    def test_duplicate_file_returns_existing_metadata(
        self, auth_client: TestClient, db_session: Session
    ):
        existing = _persisted_file(db_session)
        # The hash of b"fake image bytes" is calculated by hashlib.sha256
        import hashlib
        file_bytes = b"duplicate content"
        expected_hash = hashlib.sha256(file_bytes).hexdigest()

        # Update the existing file's hash to match what we'll upload
        with Session(engine) as s:
            db_file = s.get(UploadedFile, existing.id)
            db_file.file_hash = expected_hash
            s.add(db_file)
            s.commit()

        with (
            patch(
                "src.utils.uploads.uploads_manager.UploadsManager.get_file_mimetype",
                return_value=_FAKE_MIMETYPE,
            ),
        ):
            resp = auth_client.post(
                UPLOAD_URL,
                files={"file": ("dup.jpg", io.BytesIO(file_bytes), "image/jpeg")},
            )
        body = resp.json()
        assert resp.status_code == 200
        assert body["response"]["status"] is True
        assert "already exists" in body["response"]["message"]


# ---------------------------------------------------------------------------
# GET /uploads/get-file/{file_id}
# ---------------------------------------------------------------------------


class TestGetFile:
    def test_get_existing_file_returns_stream(
        self, client: TestClient, db_session: Session
    ):
        existing = _persisted_file(db_session)
        mock_stream = io.BytesIO(b"file content")
        mock_stream.close = MagicMock()

        with patch(
            "src.utils.uploads.uploads_manager.UploadsManager.get_file_stream",
            return_value=mock_stream,
        ):
            resp = client.get(GET_FILE_URL.format(file_id=str(existing.id)))

        assert resp.status_code == 200
        assert resp.content == b"file content"

    def test_get_nonexistent_file_returns_error(self, client: TestClient):
        resp = client.get(GET_FILE_URL.format(file_id="999999999999999"))
        assert resp.status_code == 400
