"""Integration tests for /meetings endpoints."""
import pytest
from unittest.mock import patch, MagicMock
from sqlmodel import Session
from fastapi.testclient import TestClient

from src.modules.auth.models import User
from src.modules.meetings.models import Meeting, MeetingSpeaker
from src.modules.uploads.models import UploadedFile
from src.shared.database import engine
from src.shared.enums import FileTypeEnum
from src.utils.generators import Generator

CREATE_URL = "/meetings/create_meeting"
LIST_URL = "/meetings/get_meetings"
RECORDING_URL = "/meetings/add_meeting_recording"
RECORDINGS_URL = "/meetings/get_meeting_recordings"


def _create_meeting(db_session: Session, user: User, title: str = "My Meeting") -> Meeting:
    meeting = Meeting(
        id=Generator.generate_64bit_int_uuid(),
        title=title,
        created_by_id=user.id,
    )
    db_session.add(meeting)
    db_session.commit()
    db_session.refresh(meeting)
    return meeting


def _create_uploaded_file(db_session: Session) -> UploadedFile:
    uploaded = UploadedFile(
        id=Generator.generate_64bit_int_uuid(),
        filename="audio.wav",
        content_type="audio/wav",
        size=1024,
        file_path="uploads_media/others/audio.wav",
        file_type=FileTypeEnum.AUDIO,
        file_hash="abc123uniquehash",
        mimetype="audio/wav",
    )
    db_session.add(uploaded)
    db_session.commit()
    db_session.refresh(uploaded)
    return uploaded


# ---------------------------------------------------------------------------
# Create meeting
# ---------------------------------------------------------------------------


class TestCreateMeeting:
    def test_create_meeting_success(self, auth_client: TestClient, user: User):
        resp = auth_client.post(
            CREATE_URL,
            json={"title": "Sprint Planning", "description": "Weekly planning session"},
        )
        body = resp.json()
        assert resp.status_code == 200
        assert body["response"]["status"] is True
        assert body["data"]["title"] == "Sprint Planning"

    def test_create_meeting_without_auth_fails(self, client: TestClient):
        resp = client.post(
            CREATE_URL,
            json={"title": "Sprint Planning"},
        )
        assert resp.status_code in (401, 403)

    def test_create_meeting_title_too_short_fails(self, auth_client: TestClient):
        resp = auth_client.post(CREATE_URL, json={"title": "AB"})  # < 3 chars
        assert resp.status_code == 422

    def test_create_meeting_persists_in_db(
        self, auth_client: TestClient, user: User, db_session: Session
    ):
        auth_client.post(
            CREATE_URL, json={"title": "Persistence Check"}
        )
        meeting = db_session.exec(
            __import__("sqlmodel").select(Meeting).where(Meeting.title == "Persistence Check")
        ).first()
        assert meeting is not None
        assert meeting.created_by_id == user.id


# ---------------------------------------------------------------------------
# Get meetings
# ---------------------------------------------------------------------------


class TestGetMeetings:
    def test_returns_only_own_meetings(
        self,
        client: TestClient,
        db_session: Session,
        user: User,
        second_user: User,
    ):
        from app import app
        from src.shared.dependencies import get_current_user

        # Create one meeting per user
        _create_meeting(db_session, user, title="User Meeting")
        _create_meeting(db_session, second_user, title="Other User Meeting")

        # Act as `user`
        app.dependency_overrides[get_current_user] = lambda: user
        resp = client.get(LIST_URL)
        app.dependency_overrides.clear()

        body = resp.json()
        assert resp.status_code == 200
        titles = [m["title"] for m in body["data"]]
        assert "User Meeting" in titles
        assert "Other User Meeting" not in titles

    def test_pagination_page_size(
        self, auth_client: TestClient, db_session: Session, user: User
    ):
        for i in range(5):
            _create_meeting(db_session, user, title=f"Meeting {i}")

        resp = auth_client.get(LIST_URL, params={"pageNumber": 1, "itemsPerPage": 2})
        body = resp.json()
        assert len(body["data"]) == 2

    def test_requires_auth(self, client: TestClient):
        resp = client.get(LIST_URL)
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Add meeting recording
# ---------------------------------------------------------------------------


class TestAddMeetingRecording:
    def test_add_recording_calls_diarization(
        self, auth_client: TestClient, db_session: Session, user: User
    ):
        meeting = _create_meeting(db_session, user)
        uploaded = _create_uploaded_file(db_session)

        # The speaker returned by diarization must be persisted: the real
        # service commits its speakers before the recordings that reference them,
        # and meeting_recordings.speaker_id is a foreign key.
        mock_speaker = MeetingSpeaker(
            id=Generator.generate_64bit_int_uuid(),
            speaker_name="SPEAKER_00",
            meeting_id=meeting.id,
            created_by_id=user.id,
        )
        db_session.add(mock_speaker)
        db_session.commit()
        db_session.refresh(mock_speaker)
        mock_segments = [(mock_speaker, "0.0", "5.5")]

        with (
            patch(
                "src.modules.meetings.services.SpeakerDiarizationService.diarize",
                return_value=mock_segments,
            ),
            patch(
                "src.modules.uploads.services.UploadService.download_to_path",
                return_value=(True, "OK", None),
            ),
        ):
            resp = auth_client.post(
                RECORDING_URL,
                json={
                    "meetingId": str(meeting.id),
                    "fileId": str(uploaded.id),
                    "startTime": "0.0",
                    "endTime": "5.5",
                },
            )

        body = resp.json()
        assert resp.status_code == 200
        assert body["response"]["status"] is True
        assert isinstance(body["data"], list)

    def test_add_recording_with_nonexistent_file_fails(
        self, auth_client: TestClient, db_session: Session, user: User
    ):
        meeting = _create_meeting(db_session, user)
        resp = auth_client.post(
            RECORDING_URL,
            json={
                "meetingId": str(meeting.id),
                "fileId": "999999999999999",
                "startTime": "0.0",
                "endTime": "5.5",
            },
        )
        body = resp.json()
        assert body["response"]["status"] is False

    def test_add_recording_requires_auth(
        self, client: TestClient, db_session: Session, user: User
    ):
        meeting = _create_meeting(db_session, user)
        resp = client.post(
            RECORDING_URL,
            json={
                "meetingId": str(meeting.id),
                "fileId": "1",
                "startTime": "0.0",
                "endTime": "5.5",
            },
        )
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Get meeting recordings
# ---------------------------------------------------------------------------


class TestGetMeetingRecordings:
    def test_get_recordings_for_meeting(
        self, client: TestClient, db_session: Session, user: User
    ):
        meeting = _create_meeting(db_session, user)
        resp = client.get(RECORDINGS_URL, params={"meetingId": str(meeting.id)})
        body = resp.json()
        assert resp.status_code == 200
        assert isinstance(body["data"], list)

    def test_get_recordings_missing_meeting_id_fails(self, client: TestClient):
        # meetingId is required by the DTO
        resp = client.get(RECORDINGS_URL)
        assert resp.status_code == 422
