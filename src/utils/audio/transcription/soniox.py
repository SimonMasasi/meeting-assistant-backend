"""Soniox async speech-to-text with built-in speaker diarization, via plain REST
(https://soniox.com/docs). Used when SONIOX_API_KEY is configured; replaces the
whole local Whisper + pyannote pipeline in one API call.
"""
import contextlib
import logging
import os
import time

import httpx

from config import SETTINGS
from .segments import SpeechSegment

logger = logging.getLogger(__name__)


class SonioxError(RuntimeError):
    """Raised when the Soniox API rejects or fails a transcription."""


class SonioxTranscriber:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        transport: httpx.BaseTransport | None = None,
    ):
        self.api_key = api_key or SETTINGS.SONIOX_API_KEY
        self.base_url = (base_url or SETTINGS.SONIOX_BASE_URL).rstrip("/")
        self.model = model or SETTINGS.SONIOX_MODEL
        self._transport = transport  # injectable for tests (httpx.MockTransport)

    def transcribe(
        self,
        audio: bytes | str,
        filename: str = "audio.wav",
        poll_interval_s: float = 2.0,
        timeout_s: float = 600.0,
    ) -> list[SpeechSegment]:
        """Upload the audio, run an async diarized transcription, and return the
        transcript as speaker-turn segments.

        `audio` is either the bytes or a path to a local file. With a path the
        handle is handed to httpx, which streams it, so a multi-gigabyte
        recording is never held in memory."""
        headers = {"Authorization": f"Bearer {self.api_key}"}
        file_id = transcription_id = None
        with contextlib.ExitStack() as stack:
            if isinstance(audio, (str, os.PathLike)):
                audio_body = stack.enter_context(open(audio, "rb"))
            else:
                audio_body = audio

            client = stack.enter_context(httpx.Client(
                base_url=self.base_url, headers=headers, timeout=60, transport=self._transport
            ))
            try:
                resp = client.post("/v1/files", files={"file": (filename, audio_body)})
                _raise_for_status(resp, "file upload")
                file_id = resp.json()["id"]

                resp = client.post(
                    "/v1/transcriptions",
                    json={
                        "model": self.model,
                        "file_id": file_id,
                        "enable_speaker_diarization": True,
                    },
                )
                _raise_for_status(resp, "create transcription")
                transcription_id = resp.json()["id"]

                deadline = time.monotonic() + timeout_s
                while True:
                    resp = client.get(f"/v1/transcriptions/{transcription_id}")
                    _raise_for_status(resp, "poll transcription")
                    body = resp.json()
                    if body["status"] == "completed":
                        break
                    if body["status"] == "error":
                        raise SonioxError(
                            "Soniox transcription failed: "
                            f"{body.get('error_type')}: {body.get('error_message')}"
                        )
                    if time.monotonic() > deadline:
                        raise SonioxError(
                            f"Soniox transcription timed out after {timeout_s:.0f}s"
                        )
                    time.sleep(poll_interval_s)

                resp = client.get(f"/v1/transcriptions/{transcription_id}/transcript")
                _raise_for_status(resp, "fetch transcript")
                tokens = resp.json().get("tokens", [])
            finally:
                # Best-effort cleanup so audio doesn't linger in Soniox storage.
                cleanup = [f"/v1/transcriptions/{transcription_id}"] if transcription_id else []
                cleanup += [f"/v1/files/{file_id}"] if file_id else []
                for path in cleanup:
                    try:
                        client.delete(path)
                    except httpx.HTTPError:
                        logger.warning("Soniox cleanup failed for %s", path)
        return group_tokens_into_segments(tokens)


def _raise_for_status(resp: httpx.Response, step: str) -> None:
    if resp.status_code >= 400:
        raise SonioxError(f"Soniox {step} failed ({resp.status_code}): {resp.text[:300]}")


def group_tokens_into_segments(tokens: list[dict], split_gap_ms: int = 2000) -> list[SpeechSegment]:
    """Group Soniox sub-word tokens into speaker-turn segments. A new segment
    starts on speaker change or a silence gap longer than split_gap_ms. Tokens
    carry their own leading spaces, so texts concatenate directly."""
    segments: list[SpeechSegment] = []
    current: SpeechSegment | None = None

    def flush():
        if current is not None and current.text.strip():
            current.text = current.text.strip()
            segments.append(current)

    for tok in tokens:
        text = tok.get("text") or ""
        if not text:
            continue
        speaker = tok.get("speaker")
        speaker = str(speaker) if speaker is not None else None
        start_ms = int(tok.get("start_ms") or 0)
        end_ms = int(tok.get("end_ms") or start_ms)
        if (
            current is None
            or speaker != current.speaker_key
            or start_ms - current.end_ms > split_gap_ms
        ):
            flush()
            current = SpeechSegment(
                speaker_key=speaker, start_ms=start_ms, end_ms=end_ms, text=text
            )
        else:
            current.text += text
            current.end_ms = end_ms
    flush()
    return segments
