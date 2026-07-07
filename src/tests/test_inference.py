"""Integration tests for /inference transcription: provider selection (Soniox
vs local Whisper + pyannote), persistence, and transcript read-back."""
import io
import logging
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from config import SETTINGS
from src.modules.auth.models import User
from src.modules.meetings.models import Meeting, MeetingRecording, MeetingSpeaker
from src.modules.uploads.models import UploadedFile
from src.shared.database import engine
from src.shared.enums import FileTypeEnum
from src.utils.audio.transcription.segments import SpeechSegment
from src.utils.generators import Generator

TRANSCRIBE_URL = "/inference/transcribe/{meeting_id}"
TRANSCRIPT_URL = "/inference/transcript/{meeting_id}"

_SONIOX_SEGMENTS = [
    SpeechSegment(speaker_key="1", start_ms=0, end_ms=4000, text="Hello everyone."),
    SpeechSegment(speaker_key="2", start_ms=4500, end_ms=8000, text="Hi, thanks for joining."),
    SpeechSegment(speaker_key="1", start_ms=8500, end_ms=12000, text="Let's get started."),
]


def _persisted_meeting(db_session: Session, user: User) -> Meeting:
    meeting = Meeting(title="Weekly sync", created_by_id=user.id)
    db_session.add(meeting)
    db_session.commit()
    db_session.refresh(meeting)
    return meeting


def _persisted_audio_file(db_session: Session) -> UploadedFile:
    f = UploadedFile(
        id=Generator.generate_64bit_int_uuid(),
        filename="meeting.wav",
        content_type="audio/wav",
        size=1024,
        file_path="uploads_media/audio/meeting.wav",
        file_type=FileTypeEnum.AUDIO,
        file_hash="uniquehash_audio",
        mimetype="audio/wav",
    )
    db_session.add(f)
    db_session.commit()
    db_session.refresh(f)
    return f


def _get_file_patch(file_row: UploadedFile):
    return patch(
        "src.modules.uploads.services.UploadService.get_file",
        return_value=(True, "ok", io.BytesIO(b"fake-audio-bytes"), file_row),
    )


def _fake_whisper(asr_lines: list[tuple[float, float, str]]):
    """A stand-in for the faster-whisper model: .transcribe() -> (segments, info)."""
    whisper = MagicMock()
    whisper.transcribe.return_value = (
        [SimpleNamespace(start=s, end=e, text=t) for s, e, t in asr_lines],
        None,
    )
    return whisper


def _post_transcribe(auth_client: TestClient, meeting: Meeting, file_row: UploadedFile):
    return auth_client.post(
        TRANSCRIBE_URL.format(meeting_id=str(meeting.id)),
        json={"fileId": str(file_row.id)},
    )


class TestProviderSelection:
    def test_soniox_used_when_api_key_set(self, auth_client, db_session, user, monkeypatch):
        monkeypatch.setattr(SETTINGS, "SONIOX_API_KEY", "test-key")
        meeting = _persisted_meeting(db_session, user)
        file_row = _persisted_audio_file(db_session)

        with (
            _get_file_patch(file_row),
            patch(
                "src.modules.inference.services.SonioxTranscriber.transcribe",
                return_value=list(_SONIOX_SEGMENTS),
            ) as soniox_mock,
            patch(
                "src.utils.audio.speaker_diarization.SpeakerDiarizationService.diarize_turns"
            ) as diarize_mock,
            patch(
                "src.modules.inference.services.InferenceService._load_whisper"
            ) as whisper_mock,
        ):
            resp = _post_transcribe(auth_client, meeting, file_row)

        body = resp.json()
        assert resp.status_code == 200
        assert body["response"]["status"] is True
        soniox_mock.assert_called_once()
        diarize_mock.assert_not_called()
        whisper_mock.assert_not_called()

        # Soniox speakers "1"/"2" become display names "Speaker 1"/"Speaker 2".
        assert [seg["speakerLabel"] for seg in body["data"]] == [
            "Speaker 1", "Speaker 2", "Speaker 1",
        ]
        assert body["data"][0]["startMs"] == 0
        assert body["data"][0]["text"] == "Hello everyone."

        with Session(engine) as session:
            recordings = session.exec(select(MeetingRecording)).all()
            speakers = session.exec(select(MeetingSpeaker)).all()
        assert len(recordings) == 3
        assert all(r.text for r in recordings)
        assert recordings[0].start_time == "0.0" and recordings[0].end_time == "4.0"
        assert {s.speaker_name for s in speakers} == {"Speaker 1", "Speaker 2"}

    def test_local_pipeline_used_when_key_unset(self, auth_client, db_session, user, monkeypatch):
        monkeypatch.setattr(SETTINGS, "SONIOX_API_KEY", "")
        meeting = _persisted_meeting(db_session, user)
        file_row = _persisted_audio_file(db_session)

        with (
            _get_file_patch(file_row),
            patch(
                "src.modules.inference.services.SonioxTranscriber.transcribe"
            ) as soniox_mock,
            patch(
                "src.utils.audio.speaker_diarization.SpeakerDiarizationService.diarize_turns",
                return_value=[("SPEAKER_00", 0.0, 5.0), ("SPEAKER_01", 5.0, 10.0)],
            ),
            patch(
                "src.modules.inference.services.InferenceService._load_whisper",
                return_value=_fake_whisper([(0.0, 4.0, "Hello."), (5.5, 9.0, "Hi there.")]),
            ),
        ):
            resp = _post_transcribe(auth_client, meeting, file_row)

        body = resp.json()
        assert resp.status_code == 200
        assert body["response"]["status"] is True
        soniox_mock.assert_not_called()
        assert [seg["speakerLabel"] for seg in body["data"]] == ["Speaker 1", "Speaker 2"]
        assert body["data"][0]["startMs"] == 0 and body["data"][0]["endMs"] == 4000

    def test_falls_back_to_local_when_soniox_fails(
        self, auth_client, db_session, user, monkeypatch, caplog
    ):
        monkeypatch.setattr(SETTINGS, "SONIOX_API_KEY", "test-key")
        meeting = _persisted_meeting(db_session, user)
        file_row = _persisted_audio_file(db_session)

        from src.utils.audio.transcription.soniox import SonioxError

        with (
            _get_file_patch(file_row),
            patch(
                "src.modules.inference.services.SonioxTranscriber.transcribe",
                side_effect=SonioxError("Soniox file upload failed (503): unavailable"),
            ) as soniox_mock,
            patch(
                "src.utils.audio.speaker_diarization.SpeakerDiarizationService.diarize_turns",
                return_value=[("SPEAKER_00", 0.0, 5.0)],
            ) as diarize_mock,
            patch(
                "src.modules.inference.services.InferenceService._load_whisper",
                return_value=_fake_whisper([(0.0, 4.0, "Hello.")]),
            ),
            caplog.at_level(logging.WARNING, logger="src.modules.inference.services"),
        ):
            resp = _post_transcribe(auth_client, meeting, file_row)

        body = resp.json()
        assert resp.status_code == 200
        assert body["response"]["status"] is True
        soniox_mock.assert_called_once()
        diarize_mock.assert_called_once()
        assert any("falling back to local pipeline" in r.message for r in caplog.records)
        assert [seg["text"] for seg in body["data"]] == ["Hello."]


class TestPersistence:
    def test_retranscribing_replaces_rows_without_duplicates(
        self, auth_client, db_session, user, monkeypatch
    ):
        monkeypatch.setattr(SETTINGS, "SONIOX_API_KEY", "test-key")
        meeting = _persisted_meeting(db_session, user)
        file_row = _persisted_audio_file(db_session)

        with (
            _get_file_patch(file_row),
            patch(
                "src.modules.inference.services.SonioxTranscriber.transcribe",
                return_value=list(_SONIOX_SEGMENTS),
            ),
        ):
            first = _post_transcribe(auth_client, meeting, file_row)
            second = _post_transcribe(auth_client, meeting, file_row)

        assert first.json()["response"]["status"] is True
        assert second.json()["response"]["status"] is True

        with Session(engine) as session:
            recordings = session.exec(select(MeetingRecording)).all()
            speakers = session.exec(select(MeetingSpeaker)).all()
        assert len(recordings) == 3  # replaced, not appended
        assert len(speakers) == 2  # no orphaned speakers from the first run

    def test_unknown_speaker_segments_persist_with_null_speaker(
        self, auth_client, db_session, user, monkeypatch
    ):
        monkeypatch.setattr(SETTINGS, "SONIOX_API_KEY", "test-key")
        meeting = _persisted_meeting(db_session, user)
        file_row = _persisted_audio_file(db_session)
        segments = [SpeechSegment(speaker_key=None, start_ms=0, end_ms=1000, text="Uncredited.")]

        with (
            _get_file_patch(file_row),
            patch(
                "src.modules.inference.services.SonioxTranscriber.transcribe",
                return_value=segments,
            ),
        ):
            resp = _post_transcribe(auth_client, meeting, file_row)

        body = resp.json()
        assert body["data"][0]["speakerLabel"] == "Unknown speaker"
        assert body["data"][0]["speakerName"] is None
        with Session(engine) as session:
            recording = session.exec(select(MeetingRecording)).one()
            assert recording.speaker_id is None
            assert session.exec(select(MeetingSpeaker)).all() == []


class TestGetTranscript:
    def test_round_trip_returns_sorted_segments(self, auth_client, db_session, user, monkeypatch):
        monkeypatch.setattr(SETTINGS, "SONIOX_API_KEY", "test-key")
        meeting = _persisted_meeting(db_session, user)
        file_row = _persisted_audio_file(db_session)
        # Deliberately out of order; read-back must sort by start.
        segments = [_SONIOX_SEGMENTS[2], _SONIOX_SEGMENTS[0], _SONIOX_SEGMENTS[1]]

        with (
            _get_file_patch(file_row),
            patch(
                "src.modules.inference.services.SonioxTranscriber.transcribe",
                return_value=segments,
            ),
        ):
            _post_transcribe(auth_client, meeting, file_row)

        resp = auth_client.get(TRANSCRIPT_URL.format(meeting_id=str(meeting.id)))
        body = resp.json()
        assert resp.status_code == 200
        assert body["response"]["status"] is True
        starts = [seg["startMs"] for seg in body["data"]]
        assert starts == sorted(starts) == [0, 4500, 8500]
        assert [seg["text"] for seg in body["data"]] == [
            "Hello everyone.", "Hi, thanks for joining.", "Let's get started.",
        ]
