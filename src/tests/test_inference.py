"""Integration tests for /inference transcription: provider selection (Soniox
vs local Whisper + pyannote), persistence, and transcript read-back."""
import io
import logging
import wave
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
UTTERANCE_URL = "/inference/transcribe-utterance"

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
    """Transcription streams the recording to a local temp path rather than
    reading it into memory, so this stubs the download instead of the read."""
    return patch(
        "src.modules.uploads.services.UploadService.download_to_path",
        return_value=(True, "ok", file_row),
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


def _wav_bytes(seconds: float = 1.0, sample_rate: int = 16000) -> bytes:
    """A valid 16 kHz mono 16-bit PCM WAV of silence — the exact format the
    desktop client sends. Only the header is read for the duration guard."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\x00\x00" * int(sample_rate * seconds))
    return buf.getvalue()


def _post_utterance(auth_client: TestClient, audio: bytes, language: str | None = None):
    url = UTTERANCE_URL if language is None else f"{UTTERANCE_URL}?language={language}"
    return auth_client.post(url, files={"file": ("utterance.wav", io.BytesIO(audio), "audio/wav")})


class TestTranscribeUtterance:
    def test_returns_trimmed_text_and_metadata(self, auth_client):
        with patch(
            "src.modules.inference.services.InferenceService._utterance_text",
            return_value=("  so what we agreed on last week  ", "en", 0.98),
        ) as stt:
            resp = _post_utterance(auth_client, _wav_bytes(seconds=2.0), language="en")

        body = resp.json()
        assert resp.status_code == 200
        assert body["response"]["status"] is True
        assert body["response"]["message"] == "Transcribed"
        assert body["data"]["text"] == "so what we agreed on last week"
        assert body["data"]["durationMs"] == 2000
        assert body["data"]["language"] == "en"
        assert body["data"]["confidence"] == 0.98
        stt.assert_called_once()

    def test_silence_returns_empty_text_not_error(self, auth_client):
        # The client's VAD has false positives; empty must be status:true, no 4xx.
        with patch(
            "src.modules.inference.services.InferenceService._utterance_text",
            return_value=("", None, None),
        ):
            resp = _post_utterance(auth_client, _wav_bytes(seconds=0.5))

        body = resp.json()
        assert resp.status_code == 200
        assert body["response"]["status"] is True
        assert body["data"]["text"] == ""

    def test_language_query_param_is_passed_through(self, auth_client):
        with patch(
            "src.modules.inference.services.InferenceService._utterance_text",
            return_value=("hola", "es", None),
        ) as stt:
            _post_utterance(auth_client, _wav_bytes(), language="es")
        assert stt.call_args.args[2] == "es"

    def test_defaults_language_to_en(self, auth_client):
        with patch(
            "src.modules.inference.services.InferenceService._utterance_text",
            return_value=("hi", None, None),
        ) as stt:
            _post_utterance(auth_client, _wav_bytes())
        assert stt.call_args.args[2] == "en"

    def test_rejects_oversize_audio(self, auth_client):
        # Over 2 MB: status false with a readable message, and STT never runs.
        big = b"\x00" * (2 * 1024 * 1024 + 1)
        with patch(
            "src.modules.inference.services.InferenceService._utterance_text"
        ) as stt:
            resp = _post_utterance(auth_client, big)

        body = resp.json()
        assert resp.status_code == 200
        assert body["response"]["status"] is False
        assert "MB limit" in body["response"]["message"]
        assert body["data"] is None
        stt.assert_not_called()

    def test_rejects_audio_longer_than_60s(self, auth_client):
        with patch(
            "src.modules.inference.services.InferenceService._utterance_text"
        ) as stt:
            resp = _post_utterance(auth_client, _wav_bytes(seconds=61))

        body = resp.json()
        assert body["response"]["status"] is False
        assert "60 s limit" in body["response"]["message"]
        stt.assert_not_called()

    def test_rejects_non_wav_body(self, auth_client):
        with patch(
            "src.modules.inference.services.InferenceService._utterance_text"
        ) as stt:
            resp = _post_utterance(auth_client, b"this is not a wav file at all")

        body = resp.json()
        assert body["response"]["status"] is False
        assert "WAV" in body["response"]["message"]
        stt.assert_not_called()

    def test_backend_failure_is_readable_not_500(self, auth_client):
        with patch(
            "src.modules.inference.services.InferenceService._utterance_text",
            side_effect=RuntimeError("connection refused"),
        ):
            resp = _post_utterance(auth_client, _wav_bytes())

        body = resp.json()
        assert resp.status_code == 200
        assert body["response"]["status"] is False
        assert body["data"] is None

    def test_writes_nothing_to_transcript_store(self, auth_client):
        with patch(
            "src.modules.inference.services.InferenceService._utterance_text",
            return_value=("some words", "en", None),
        ):
            _post_utterance(auth_client, _wav_bytes())

        with Session(engine) as session:
            assert session.exec(select(MeetingRecording)).all() == []
            assert session.exec(select(MeetingSpeaker)).all() == []

    def test_requires_authentication(self, client):
        resp = client.post(
            UTTERANCE_URL,
            files={"file": ("utterance.wav", io.BytesIO(_wav_bytes()), "audio/wav")},
        )
        assert resp.status_code in (401, 403)
