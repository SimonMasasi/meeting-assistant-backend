"""Unit tests for the Soniox transcription client (no app / DB needed)."""
import httpx
import pytest

from src.utils.audio.transcription.segments import SpeechSegment
from src.utils.audio.transcription.soniox import (
    SonioxError,
    SonioxTranscriber,
    group_tokens_into_segments,
)


# ---------------------------------------------------------------------------
# group_tokens_into_segments
# ---------------------------------------------------------------------------


class TestGroupTokensIntoSegments:
    def test_merges_subword_tokens_of_same_speaker(self):
        tokens = [
            {"text": "Hel", "start_ms": 0, "end_ms": 100, "speaker": "1"},
            {"text": "lo", "start_ms": 100, "end_ms": 200, "speaker": "1"},
            {"text": " there", "start_ms": 200, "end_ms": 400, "speaker": "1"},
        ]
        segments = group_tokens_into_segments(tokens)
        assert segments == [
            SpeechSegment(speaker_key="1", start_ms=0, end_ms=400, text="Hello there")
        ]

    def test_splits_on_speaker_change(self):
        tokens = [
            {"text": "Hi", "start_ms": 0, "end_ms": 100, "speaker": "1"},
            {"text": " Bob", "start_ms": 100, "end_ms": 300, "speaker": "1"},
            {"text": "Hey", "start_ms": 350, "end_ms": 500, "speaker": "2"},
        ]
        segments = group_tokens_into_segments(tokens)
        assert [s.speaker_key for s in segments] == ["1", "2"]
        assert [s.text for s in segments] == ["Hi Bob", "Hey"]
        assert segments[0].end_ms == 300 and segments[1].start_ms == 350

    def test_splits_on_long_silence_gap(self):
        tokens = [
            {"text": "First", "start_ms": 0, "end_ms": 500, "speaker": "1"},
            {"text": "Second", "start_ms": 5000, "end_ms": 5500, "speaker": "1"},
        ]
        segments = group_tokens_into_segments(tokens, split_gap_ms=2000)
        assert [s.text for s in segments] == ["First", "Second"]

    def test_int_and_str_speaker_ids_normalize_to_same_key(self):
        tokens = [
            {"text": "a", "start_ms": 0, "end_ms": 100, "speaker": 1},
            {"text": "b", "start_ms": 100, "end_ms": 200, "speaker": "1"},
        ]
        segments = group_tokens_into_segments(tokens)
        assert len(segments) == 1
        assert segments[0].speaker_key == "1"

    def test_tokens_without_speaker_keep_none_key(self):
        tokens = [{"text": "hello", "start_ms": 0, "end_ms": 100}]
        segments = group_tokens_into_segments(tokens)
        assert segments == [
            SpeechSegment(speaker_key=None, start_ms=0, end_ms=100, text="hello")
        ]

    def test_empty_token_list(self):
        assert group_tokens_into_segments([]) == []

    def test_whitespace_only_segments_are_dropped(self):
        tokens = [
            {"text": " ", "start_ms": 0, "end_ms": 100, "speaker": "1"},
            {"text": "real", "start_ms": 3000, "end_ms": 3100, "speaker": "2"},
        ]
        segments = group_tokens_into_segments(tokens)
        assert [s.text for s in segments] == ["real"]


# ---------------------------------------------------------------------------
# SonioxTranscriber (httpx.MockTransport — no network)
# ---------------------------------------------------------------------------

_TRANSCRIPT_BODY = {
    "id": "tr-1",
    "text": "Hello there",
    "tokens": [
        {"text": "Hello", "start_ms": 0, "end_ms": 400, "confidence": 0.99, "speaker": "1"},
        {"text": " there", "start_ms": 400, "end_ms": 700, "confidence": 0.98, "speaker": "1"},
        {"text": "Hi", "start_ms": 900, "end_ms": 1100, "confidence": 0.97, "speaker": "2"},
    ],
}


def _mock_transport(recorded: list, poll_statuses=("processing", "completed"),
                    transcript_body=_TRANSCRIPT_BODY):
    """MockTransport driving the full upload → create → poll → transcript flow."""
    polls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        recorded.append((request.method, request.url.path, request))
        if request.method == "POST" and request.url.path == "/v1/files":
            return httpx.Response(201, json={"id": "file-1", "filename": "audio.wav"})
        if request.method == "POST" and request.url.path == "/v1/transcriptions":
            return httpx.Response(201, json={"id": "tr-1", "status": "queued"})
        if request.method == "GET" and request.url.path == "/v1/transcriptions/tr-1":
            status = poll_statuses[min(polls["count"], len(poll_statuses) - 1)]
            polls["count"] += 1
            return httpx.Response(200, json={
                "id": "tr-1", "status": status,
                "error_type": "transcription_error", "error_message": "boom",
            })
        if request.method == "GET" and request.url.path == "/v1/transcriptions/tr-1/transcript":
            return httpx.Response(200, json=transcript_body)
        if request.method == "DELETE":
            return httpx.Response(204)
        return httpx.Response(404, json={"message": "not found"})

    return httpx.MockTransport(handler)


def _transcriber(transport: httpx.BaseTransport) -> SonioxTranscriber:
    return SonioxTranscriber(
        api_key="test-key",
        base_url="https://api.soniox.test",
        model="stt-async-v5",
        transport=transport,
    )


class TestSonioxTranscriber:
    def test_happy_path_request_sequence_and_segments(self):
        recorded: list = []
        transcriber = _transcriber(_mock_transport(recorded))

        segments = transcriber.transcribe(b"fake-audio", filename="meeting.wav",
                                          poll_interval_s=0)

        assert [(m, p) for m, p, _ in recorded] == [
            ("POST", "/v1/files"),
            ("POST", "/v1/transcriptions"),
            ("GET", "/v1/transcriptions/tr-1"),   # processing
            ("GET", "/v1/transcriptions/tr-1"),   # completed
            ("GET", "/v1/transcriptions/tr-1/transcript"),
            ("DELETE", "/v1/transcriptions/tr-1"),
            ("DELETE", "/v1/files/file-1"),
        ]
        create_request = recorded[1][2]
        assert (
            b'"model": "stt-async-v5"' in create_request.content
            or b'"model":"stt-async-v5"' in create_request.content
        )
        assert b'"file_id"' in create_request.content
        assert b'"enable_speaker_diarization"' in create_request.content
        assert recorded[0][2].headers["Authorization"] == "Bearer test-key"

        assert segments == [
            SpeechSegment(speaker_key="1", start_ms=0, end_ms=700, text="Hello there"),
            SpeechSegment(speaker_key="2", start_ms=900, end_ms=1100, text="Hi"),
        ]

    def test_error_status_raises_and_still_cleans_up(self):
        recorded: list = []
        transcriber = _transcriber(_mock_transport(recorded, poll_statuses=("error",)))

        with pytest.raises(SonioxError, match="transcription_error: boom"):
            transcriber.transcribe(b"fake-audio", poll_interval_s=0)

        deletes = [(m, p) for m, p, _ in recorded if m == "DELETE"]
        assert deletes == [
            ("DELETE", "/v1/transcriptions/tr-1"),
            ("DELETE", "/v1/files/file-1"),
        ]

    def test_http_error_raises_soniox_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"message": "invalid api key"})

        transcriber = _transcriber(httpx.MockTransport(handler))
        with pytest.raises(SonioxError, match="file upload failed \\(401\\)"):
            transcriber.transcribe(b"fake-audio")

    def test_timeout_raises_soniox_error(self):
        recorded: list = []
        transcriber = _transcriber(_mock_transport(recorded, poll_statuses=("processing",)))

        with pytest.raises(SonioxError, match="timed out"):
            transcriber.transcribe(b"fake-audio", poll_interval_s=0, timeout_s=0)
