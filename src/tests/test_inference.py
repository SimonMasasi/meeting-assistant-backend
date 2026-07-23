"""Integration tests for /inference transcription: provider selection (Soniox
vs local Whisper + pyannote), persistence, and transcript read-back."""
import io
import json
import logging
import time
import wave
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from config import SETTINGS
from src.modules.auth.models import User
from src.modules.inference.services import InferenceService, _audio_duration_ms
from src.modules.meetings.models import Meeting, MeetingRecording, MeetingSpeaker
from src.modules.uploads.models import UploadedFile
from src.shared.database import engine
from src.shared.enums import FileTypeEnum
from src.utils.audio.transcription.segments import SpeechSegment
from src.utils.generators import Generator

TRANSCRIBE_URL = "/inference/transcribe/{meeting_id}"
TRANSCRIBE_STREAM_URL = "/inference/transcribe-stream/{meeting_id}"
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


def _duration_patch(ms: int | None):
    """Stub the audio length. The download is mocked, so there is no real file on
    disk for the header read to work on."""
    return patch("src.modules.inference.services._audio_duration_ms", return_value=ms)


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


def _post_transcribe_stream(auth_client: TestClient, meeting: Meeting, file_row: UploadedFile):
    return auth_client.post(
        TRANSCRIBE_STREAM_URL.format(meeting_id=str(meeting.id)),
        json={"fileId": str(file_row.id)},
    )


def _parse_sse(body: str) -> list[tuple[str, dict]]:
    """(event, data) pairs from an SSE body. TestClient buffers the whole
    response, so ordering is all that can be asserted here, not timing."""
    events = []
    for frame in body.split("\n\n"):
        lines = [line for line in frame.splitlines() if line]
        if not lines:
            continue
        name = next(line[len("event: "):] for line in lines if line.startswith("event: "))
        data = next(line[len("data: "):] for line in lines if line.startswith("data: "))
        events.append((name, json.loads(data)))
    return events


def _events_named(events: list[tuple[str, dict]], name: str) -> list[dict]:
    return [payload for event, payload in events if event == name]


class TestTranscribeStream:
    def test_local_backend_streams_segments_then_done(
        self, auth_client, db_session, user, monkeypatch
    ):
        monkeypatch.setattr(SETTINGS, "SONIOX_API_KEY", "")
        meeting = _persisted_meeting(db_session, user)
        file_row = _persisted_audio_file(db_session)

        with (
            _get_file_patch(file_row),
            patch(
                "src.utils.audio.speaker_diarization.SpeakerDiarizationService.diarize_turns",
                return_value=[("SPEAKER_00", 0.0, 5.0), ("SPEAKER_01", 5.0, 10.0)],
            ),
            patch(
                "src.modules.inference.services.InferenceService._load_whisper",
                return_value=_fake_whisper([(0.0, 4.0, "Hello."), (5.5, 9.0, "Hi there.")]),
            ),
        ):
            resp = _post_transcribe_stream(auth_client, meeting, file_row)

        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        events = _parse_sse(resp.text)

        segments = _events_named(events, "segment")
        assert [s["index"] for s in segments] == [0, 1]
        assert [s["text"] for s in segments] == ["Hello.", "Hi there."]
        assert [s["speakerLabel"] for s in segments] == ["Speaker 1", "Speaker 2"]
        assert [s["startMs"] for s in segments] == [0, 5500]

        stages = [p["stage"] for p in _events_named(events, "status")]
        assert stages == ["downloading", "diarizing", "transcribing", "saving"]
        assert _events_named(events, "progress")[0]["processedMs"] == 4000
        assert _events_named(events, "done") == [{"segmentCount": 2}]
        # done is terminal.
        assert events[-1][0] == "done"

    def test_soniox_backend_heartbeats_then_streams_segments(
        self, auth_client, db_session, user, monkeypatch
    ):
        monkeypatch.setattr(SETTINGS, "SONIOX_API_KEY", "test-key")
        # Soniox has no partials, so the wait is spent on heartbeats; shorten the
        # interval so the test doesn't sit through a real one.
        monkeypatch.setattr("src.modules.inference.services.STREAM_HEARTBEAT_S", 0.01)
        meeting = _persisted_meeting(db_session, user)
        file_row = _persisted_audio_file(db_session)

        def slow_transcribe(*args, **kwargs):
            time.sleep(0.05)
            return list(_SONIOX_SEGMENTS)

        with (
            _get_file_patch(file_row),
            _duration_patch(27_000),
            patch(
                "src.modules.inference.services.SonioxTranscriber.transcribe",
                side_effect=slow_transcribe,
            ),
            patch(
                "src.utils.audio.speaker_diarization.SpeakerDiarizationService.diarize_turns"
            ) as diarize_mock,
        ):
            resp = _post_transcribe_stream(auth_client, meeting, file_row)

        events = _parse_sse(resp.text)
        diarize_mock.assert_not_called()
        statuses = _events_named(events, "status")
        assert [p["stage"] for p in statuses] == ["downloading", "transcribing", "saving"]
        assert {p["backend"] for p in statuses} == {None, "soniox"}
        # No position is knowable on this path, but the audio's length is, and
        # heartbeats keep a proxy from closing an idle connection mid-job.
        heartbeats = _events_named(events, "progress")
        assert heartbeats and all(h["processedMs"] is None for h in heartbeats)
        assert all(h["totalMs"] == 27_000 for h in heartbeats)
        assert [s["speakerLabel"] for s in _events_named(events, "segment")] == [
            "Speaker 1", "Speaker 2", "Speaker 1",
        ]
        assert _events_named(events, "done") == [{"segmentCount": 3}]

    def test_falls_back_to_local_when_soniox_fails(
        self, auth_client, db_session, user, monkeypatch
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
            ),
            patch(
                "src.utils.audio.speaker_diarization.SpeakerDiarizationService.diarize_turns",
                return_value=[("SPEAKER_00", 0.0, 5.0)],
            ),
            patch(
                "src.modules.inference.services.InferenceService._load_whisper",
                return_value=_fake_whisper([(0.0, 4.0, "Hello.")]),
            ),
        ):
            resp = _post_transcribe_stream(auth_client, meeting, file_row)

        events = _parse_sse(resp.text)
        backends = [p["backend"] for p in _events_named(events, "status")]
        assert "soniox" in backends and backends[-1] == "local"
        assert [s["text"] for s in _events_named(events, "segment")] == ["Hello."]
        assert _events_named(events, "done") == [{"segmentCount": 1}]

    def test_streamed_segments_match_what_is_persisted(
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
            streamed = _events_named(_parse_sse(_post_transcribe_stream(auth_client, meeting, file_row).text), "segment")

        stored = auth_client.get(TRANSCRIPT_URL.format(meeting_id=str(meeting.id))).json()["data"]
        assert [(s["speakerLabel"], s["text"]) for s in stored] == [
            (s["speakerLabel"], s["text"]) for s in streamed
        ]

    def test_restreaming_replaces_rows_and_keeps_labels_stable(
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
            _post_transcribe_stream(auth_client, meeting, file_row)
            second = _parse_sse(_post_transcribe_stream(auth_client, meeting, file_row).text)

        # The second run's speakers replace the first run's, so numbering restarts
        # rather than climbing to "Speaker 3".
        assert [s["speakerLabel"] for s in _events_named(second, "segment")] == [
            "Speaker 1", "Speaker 2", "Speaker 1",
        ]
        with Session(engine) as session:
            assert len(session.exec(select(MeetingRecording)).all()) == 3
            assert len(session.exec(select(MeetingSpeaker)).all()) == 2

    def test_failure_arrives_as_an_error_event_not_a_status_code(
        self, auth_client, db_session, user, monkeypatch
    ):
        monkeypatch.setattr(SETTINGS, "SONIOX_API_KEY", "test-key")
        meeting = _persisted_meeting(db_session, user)
        file_row = _persisted_audio_file(db_session)

        with patch(
            "src.modules.uploads.services.UploadService.download_to_path",
            return_value=(False, "File not found in storage", None),
        ):
            resp = _post_transcribe_stream(auth_client, meeting, file_row)

        events = _parse_sse(resp.text)
        # Headers are already sent by then, so the status stays 200.
        assert resp.status_code == 200
        assert _events_named(events, "error") == [{"message": "File not found in storage"}]
        assert not _events_named(events, "done")
        with Session(engine) as session:
            assert session.exec(select(MeetingRecording)).all() == []

    def test_requires_authentication(self, client):
        resp = client.post(
            TRANSCRIBE_STREAM_URL.format(meeting_id="1"), json={"fileId": "1"}
        )
        assert resp.status_code in (401, 403)

    def test_diarization_heartbeats_so_a_proxy_cannot_time_the_stream_out(
        self, auth_client, db_session, user, monkeypatch
    ):
        """Diarization runs before any segment exists and reports no position. An
        nginx/ALB idle timeout (60 s by default) would close the connection, and a
        stream that ends without `done` reads as a failure — so it must heartbeat."""
        monkeypatch.setattr(SETTINGS, "SONIOX_API_KEY", "")
        monkeypatch.setattr("src.modules.inference.services.STREAM_HEARTBEAT_S", 0.01)
        meeting = _persisted_meeting(db_session, user)
        file_row = _persisted_audio_file(db_session)

        def slow_diarize(*args, **kwargs):
            time.sleep(0.05)
            return [("SPEAKER_00", 0.0, 5.0)]

        with (
            _get_file_patch(file_row),
            _duration_patch(12_000),
            patch(
                "src.utils.audio.speaker_diarization.SpeakerDiarizationService.diarize_turns",
                side_effect=slow_diarize,
            ),
            patch(
                "src.modules.inference.services.InferenceService._load_whisper",
                return_value=_fake_whisper([(0.0, 4.0, "Hello.")]),
            ),
        ):
            events = _parse_sse(_post_transcribe_stream(auth_client, meeting, file_row).text)

        # The window that used to be dead air: between the diarizing status and
        # the transcribing one that follows it.
        stages = [p.get("stage") for _, p in events]
        start = stages.index("diarizing")
        end = stages.index("transcribing", start)
        diarizing_heartbeats = [p for name, p in events[start:end] if name == "progress"]
        assert diarizing_heartbeats, "no keep-alive was sent while diarizing"
        # The length is knowable from the file even before a position is.
        assert all(h["totalMs"] == 12_000 for h in diarizing_heartbeats)

    def test_auto_assigned_labels_are_not_reported_as_identifications(
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
            events = _parse_sse(_post_transcribe_stream(auth_client, meeting, file_row).text)

        # "Speaker 1" is a placeholder, not a name: echoing it into speakerName
        # would leave a client unable to tell an identification from its absence.
        for segment in _events_named(events, "segment"):
            assert segment["speakerLabel"].startswith("Speaker ")
            assert segment["speakerName"] is None

        stored = auth_client.get(TRANSCRIPT_URL.format(meeting_id=str(meeting.id))).json()["data"]
        assert all(s["speakerName"] is None for s in stored)

    def test_segments_are_emitted_before_asr_finishes(self, db_session, user, monkeypatch):
        """The point of the endpoint: a segment reaches the caller while
        faster-whisper is still decoding, rather than after the whole file."""
        monkeypatch.setattr(SETTINGS, "SONIOX_API_KEY", "")
        meeting = _persisted_meeting(db_session, user)
        file_row = _persisted_audio_file(db_session)

        decoded: list[str] = []

        def lazy_asr():
            for start, end, text in [(0.0, 4.0, "One."), (4.0, 8.0, "Two."), (8.0, 12.0, "Three.")]:
                decoded.append(text)
                yield SimpleNamespace(start=start, end=end, text=text)

        whisper = MagicMock()
        whisper.transcribe.return_value = (lazy_asr(), None)

        with (
            _get_file_patch(file_row),
            patch(
                "src.utils.audio.speaker_diarization.SpeakerDiarizationService.diarize_turns",
                return_value=[("SPEAKER_00", 0.0, 12.0)],
            ),
            patch(
                "src.modules.inference.services.InferenceService._load_whisper",
                return_value=whisper,
            ),
        ):
            stream = InferenceService().transcribe_iter(
                str(meeting.id), str(file_row.id), user.id
            )
            for name, payload in stream:
                if name == "segment":
                    break
            assert payload["text"] == "One."
            # Only the first line has been decoded; the rest is still pending.
            assert decoded == ["One."]
            stream.close()  # a client disconnecting mid-stream

        # Nothing was persisted, since the run never reached the saving stage.
        with Session(engine) as session:
            assert session.exec(select(MeetingRecording)).all() == []


class TestAudioDuration:
    """`_audio_duration_ms` is what lets the stream report a length during the
    stages that have no position of their own."""

    def test_reads_length_from_a_wav_header(self, tmp_path):
        path = tmp_path / "meeting.wav"
        path.write_bytes(_wav_bytes(seconds=2.5))
        assert _audio_duration_ms(str(path)) == 2500

    def test_unreadable_audio_reports_no_length(self, tmp_path):
        path = tmp_path / "not-audio.wav"
        path.write_bytes(b"this is not audio")
        # None, never an exception: a missing length must not fail the transcription.
        assert _audio_duration_ms(str(path)) is None
        assert _audio_duration_ms(str(tmp_path / "missing.wav")) is None


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
