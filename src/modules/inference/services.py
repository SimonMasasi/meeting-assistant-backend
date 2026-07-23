"""Cloud inference: transcription (Soniox cloud STT with diarization when
SONIOX_API_KEY is set, otherwise local Whisper ASR + pyannote diarization) and
summarization (any OpenAI-compatible chat endpoint).

Summarization is dependency-light (httpx) and configured purely via env
(`LLM_BASE_URL`/`LLM_API_KEY`/`LLM_MODEL`). Local transcription additionally
needs `faster-whisper` installed on the server (`uv add faster-whisper`); it is
imported lazily so the rest of the API runs without it.
"""
import concurrent.futures
import contextlib
import io
import json
import logging
import os
import re
import tempfile
import time
import wave
from typing import Iterator

import httpx
from fastapi import UploadFile
from sqlmodel import Session, select

from config import SETTINGS
from src.shared.database import engine
from src.modules.meetings.models import Meeting, MeetingRecording, MeetingSpeaker
from src.modules.uploads.services import UploadService
from src.utils.audio.speaker_diarization import SpeakerDiarizationService
from src.utils.audio.transcription.segments import SpeechSegment
from src.utils.audio.transcription.soniox import SonioxTranscriber
from .dtos import (
    SummaryDTO,
    TranscriptProgressDTO,
    TranscriptSegmentDTO,
    TranscriptSegmentEventDTO,
    TranscriptStreamDoneDTO,
    TranscriptStreamStatusDTO,
    UtteranceTranscriptDTO,
)

logger = logging.getLogger(__name__)

# How often the stream emits a progress heartbeat while a stage is running with
# nothing to report — downloading, diarizing, and the whole of the Soniox job.
# Well under the 60 s idle timeout nginx (proxy_read_timeout) and AWS ALB both
# default to: without traffic, a proxy kills the connection mid-run and the
# client correctly reports a healthy transcription as failed.
STREAM_HEARTBEAT_S = 15.0
UNKNOWN_SPEAKER_LABEL = "Unknown speaker"

# Guards for the live single-utterance endpoint. The client guarantees short
# 16 kHz mono clips; these just fence off abuse / misuse cheaply.
MAX_UTTERANCE_BYTES = 2 * 1024 * 1024
MAX_UTTERANCE_MS = 60 * 1000
# Below the client's 15 s timeout, with margin, so a slow backend surfaces as our
# own readable failure rather than a client-side transport timeout.
UTTERANCE_STT_TIMEOUT_S = 12.0

SYSTEM_PROMPT = (
    "You are an assistant that summarizes meeting transcripts. Reply with ONLY a "
    "single JSON object and nothing else, using exactly this shape: "
    '{"summary": string, "key_points": array of strings, "action_items": array of strings}. '
    '"summary" is a concise paragraph capturing what the meeting was about and what '
    'was decided. "key_points" are the most important takeaways. "action_items" are '
    "concrete follow-up tasks. Do not wrap the JSON in markdown code fences."
)


class InferenceService:
    def __init__(self):
        self.upload_service = UploadService()
        self.diarization_service = SpeakerDiarizationService()
        self._whisper = None

    # ----- Summarization (OpenAI-compatible) -------------------------------

    def summarize(self, transcript_text: str) -> SummaryDTO:
        """Summarize a transcript via the configured OpenAI-compatible endpoint."""
        if not transcript_text.strip():
            raise ValueError("No transcript to summarize yet. Record the meeting first.")
        if not SETTINGS.LLM_MODEL:
            raise ValueError("No LLM model configured. Set LLM_MODEL in the server .env.")

        url = f"{SETTINGS.LLM_BASE_URL.rstrip('/')}/chat/completions"
        headers = {"content-type": "application/json"}
        if SETTINGS.LLM_API_KEY:
            headers["authorization"] = f"Bearer {SETTINGS.LLM_API_KEY}"
        body = {
            "model": SETTINGS.LLM_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Summarize the following meeting transcript.\n\nTranscript:\n{transcript_text}"},
            ],
            "max_completion_tokens": 1024,
        }
        resp = httpx.post(url, json=body, headers=headers, timeout=120)
        if resp.status_code >= 400:
            raise ValueError(f"LLM request failed ({resp.status_code}): {resp.text[:300]}")
        content = resp.json()["choices"][0]["message"]["content"]
        parsed = _parse_summary(content)
        return SummaryDTO(
            summary=parsed["summary"],
            key_points=parsed["key_points"],
            action_items=parsed["action_items"],
            model=f"openai:{SETTINGS.LLM_MODEL}",
        )

    def summarize_meeting(self, meeting_id: str, current_user_id: int) -> SummaryDTO:
        dto = self.summarize(self._transcript_text(meeting_id))
        # Cache it on the meeting so reopening doesn't re-bill the LLM.
        with Session(engine) as session:
            meeting = session.exec(select(Meeting).where(Meeting.id == int(meeting_id))).first()
            if meeting:
                meeting.summary_json = dto.model_dump_json()
                session.add(meeting)
                session.commit()
        return dto

    def get_summary(self, meeting_id: str, current_user_id: int) -> SummaryDTO | None:
        """The cached summary for a meeting, or None if it hasn't been generated."""
        with Session(engine) as session:
            meeting = session.exec(select(Meeting).where(Meeting.id == int(meeting_id))).first()
        if not meeting or not meeting.summary_json:
            return None
        return SummaryDTO.model_validate_json(meeting.summary_json)

    # ----- Transcription (Soniox cloud, or local Whisper + diarization) ----

    def transcribe(self, meeting_id: str, file_id: str, current_user_id: int) -> list[TranscriptSegmentDTO]:
        """Transcribe + diarize an uploaded audio file, persisting one segment per
        speaker turn and returning them. Uses Soniox when SONIOX_API_KEY is set
        (falling back to the local pipeline on failure), else Whisper + pyannote.

        The blocking form of transcribe_iter: same work, same persistence, only
        the caller waits for all of it before seeing anything."""
        return [
            TranscriptSegmentDTO.model_validate(payload)
            for name, payload in self.transcribe_iter(meeting_id, file_id, current_user_id)
            if name == "segment"
        ]

    def transcribe_iter(
        self, meeting_id: str, file_id: str, current_user_id: int
    ) -> Iterator[tuple[str, dict]]:
        """Same transcription as transcribe(), yielding (event_name, payload) as
        the work proceeds so a caller can stream it to the client. Events are
        "status", "progress", "segment" and "done"; failures raise rather than
        yielding, since only the view knows how to frame them.

        Segments are persisted in one transaction at the end, not as they are
        emitted: a client that disconnects mid-run leaves the previous transcript
        untouched rather than a truncated one, and re-running is safe because
        _persist_segments replaces this file's rows.
        """
        started = time.monotonic()

        def elapsed_ms() -> int:
            return int((time.monotonic() - started) * 1000)

        # Stream the recording down to a local file rather than reading it into
        # memory: meeting audio can reach 2 GB, and every consumer below (Soniox
        # upload, pyannote, faster-whisper) accepts a path.
        # Keep the original extension so ffmpeg/torchaudio pick the right decoder.
        metadata = self.upload_service.get_file_metadata(file_id)
        suffix = os.path.splitext(metadata.filename)[1] if metadata and metadata.filename else ".wav"
        fd, audio_path = tempfile.mkstemp(suffix=suffix or ".wav")
        os.close(fd)

        collected: list[SpeechSegment] = []
        # Display names must be settled before the first segment goes out, and
        # _persist_segments has to agree with what the client already saw, so the
        # same labeler serves both.
        labeler = self._new_speaker_labeler(int(meeting_id), int(file_id))

        def emit(inner: Iterator[tuple[str, object]]) -> Iterator[tuple[str, dict]]:
            """Turn a backend's internal stream into client events, collecting the
            segments for persistence on the way through."""
            for name, payload in inner:
                if name != "_segment":
                    yield name, payload
                    continue
                segment: SpeechSegment = payload
                label = (
                    labeler.label(segment.speaker_key)
                    if segment.speaker_key is not None
                    else UNKNOWN_SPEAKER_LABEL
                )
                collected.append(segment)
                yield "segment", TranscriptSegmentEventDTO(
                    index=len(collected) - 1,
                    speaker_label=label,
                    speaker_name=_identified_name(label),
                    start_ms=segment.start_ms,
                    end_ms=segment.end_ms,
                    text=segment.text,
                ).model_dump(by_alias=True)

        try:
            yield "status", _status("downloading")
            # Pulling a multi-gigabyte recording out of storage is itself long
            # enough to trip a proxy's idle timeout, so it heartbeats too. No
            # duration is known yet — the file isn't here.
            ok, message, file_metadata = yield from _with_heartbeat(
                lambda: self.upload_service.download_to_path(file_id, audio_path),
                lambda: ("progress", _progress(None, None, elapsed_ms())),
            )
            if not ok:
                raise ValueError(message)

            # Known as soon as the audio is local, whichever backend runs it, so
            # the client can say "transcribing a 27-minute recording" during the
            # stages that report no position of their own.
            total_ms = _audio_duration_ms(audio_path)
            if total_ms:
                yield "progress", _progress(None, total_ms, elapsed_ms())

            backend = "soniox" if (SETTINGS.SONIOX_API_KEY or "").strip() else "local"
            if backend == "soniox":
                logger.info("Transcribing meeting %s file %s with Soniox", meeting_id, file_id)
                yield "status", _status("transcribing", "soniox")
                try:
                    yield from emit(
                        self._transcribe_soniox_iter(
                            audio_path,
                            file_metadata.filename if file_metadata else "audio.wav",
                            elapsed_ms,
                            total_ms,
                        )
                    )
                except Exception as e:
                    logger.warning("Soniox transcription failed (%s); falling back to local pipeline", e)
                    # Soniox only emits segments once its job completes, so a
                    # failure here means nothing reached the client yet.
                    collected.clear()
                    backend = "local"

            if backend == "local":
                logger.info("Transcribing meeting %s file %s with local Whisper + pyannote", meeting_id, file_id)
                yield from emit(self._transcribe_local_iter(audio_path, elapsed_ms, total_ms))
        finally:
            with contextlib.suppress(OSError):
                os.remove(audio_path)

        yield "status", _status("saving", backend)
        self._persist_segments(int(meeting_id), int(file_id), current_user_id, collected, labeler)
        yield "done", TranscriptStreamDoneDTO(segment_count=len(collected)).model_dump(by_alias=True)

    def _transcribe_soniox_iter(
        self, audio_path: str, filename: str, elapsed_ms, total_ms: int | None
    ) -> Iterator[tuple[str, object]]:
        """Soniox segments, preceded by heartbeats while its async job runs.

        The API returns nothing until the job completes, so the transcription
        runs in a worker thread and the wait is spent emitting progress with no
        position in it — the client should render this as indeterminate. The
        audio's length still goes out, so the wait can at least be described."""
        segments = yield from _with_heartbeat(
            lambda: SonioxTranscriber().transcribe(audio_path, filename=filename),
            lambda: ("progress", _progress(None, total_ms, elapsed_ms())),
        )
        for segment in segments:
            yield "_segment", segment

    def _transcribe_local_iter(
        self, audio_path: str, elapsed_ms, total_ms: int | None
    ) -> Iterator[tuple[str, object]]:
        # Speaker timeline first, then ASR over the whole file via faster-whisper
        # (decodes through ffmpeg); each ASR line gets its best-overlapping speaker.
        # Both stages read the file from disk, so nothing is buffered in memory.
        # Diarization needs the whole file up front, but faster-whisper yields
        # segments lazily as it decodes, so those go out as they are produced.
        yield "status", _status("diarizing", "local")
        # Minutes of work with no position to report — heartbeat, or a proxy
        # closes the connection before the first segment ever exists.
        turns = yield from _with_heartbeat(
            lambda: self.diarization_service.diarize_turns(audio_path),
            lambda: ("progress", _progress(None, total_ms, elapsed_ms())),
        )
        whisper = self._load_whisper()
        yield "status", _status("transcribing", "local")
        asr_segments, info = whisper.transcribe(audio_path)
        # Whisper's own duration is authoritative once decoding starts; the
        # header-derived one covers everything before that.
        total_ms = int((getattr(info, "duration", 0) or 0) * 1000) or total_ms
        for s in asr_segments:
            start, end, text = float(s.start), float(s.end), (s.text or "").strip()
            if text:
                yield "_segment", SpeechSegment(
                    speaker_key=_best_speaker_label(turns, start, end),
                    start_ms=int(start * 1000),
                    end_ms=int(end * 1000),
                    text=text,
                )
            yield "progress", _progress(int(end * 1000), total_ms, elapsed_ms())

    # ----- Live single-utterance transcription (stateless, no DB) ----------

    def transcribe_utterance(self, file: UploadFile, language: str = "en") -> UtteranceTranscriptDTO:
        """Transcribe one short speech utterance and return its text.

        Stateless: no meeting, no diarization, no persistence — a pure function
        from audio to text that powers cloud-mode live transcription, so it
        favors latency over batch-grade accuracy and never touches the
        transcript store. Non-speech returns an empty string (not an error) so
        the client's VAD false positives are dropped silently. Guard violations
        (too big / too long / not a WAV) raise ValueError for the view to turn
        into a readable ``status: false``."""
        file.file.seek(0, 2)
        size = file.file.tell()
        file.file.seek(0)
        if size > MAX_UTTERANCE_BYTES:
            raise ValueError(f"Audio exceeds the {MAX_UTTERANCE_BYTES // (1024 * 1024)} MB limit.")
        audio_bytes = file.file.read()

        duration_ms = _wav_duration_ms(audio_bytes)  # raises ValueError on a non-WAV body
        if duration_ms > MAX_UTTERANCE_MS:
            raise ValueError(f"Audio exceeds the {MAX_UTTERANCE_MS // 1000} s limit.")

        text, detected_language, confidence = self._utterance_text(
            audio_bytes, file.filename or "utterance.wav", language
        )
        return UtteranceTranscriptDTO(
            text=text.strip(),
            duration_ms=duration_ms,
            language=detected_language or (language or None),
            confidence=confidence,
        )

    def _utterance_text(
        self, audio_bytes: bytes, filename: str, language: str
    ) -> tuple[str, str | None, float | None]:
        """(text, detected_language, confidence) for one utterance, via the
        configured synchronous STT backend (cloud when STT_BASE_URL is set, else
        the local Whisper model — no diarization on either path)."""
        if SETTINGS.STT_BASE_URL and SETTINGS.STT_BASE_URL.strip():
            return self._utterance_text_cloud(audio_bytes, filename, language)
        return self._utterance_text_local(audio_bytes, language)

    def _utterance_text_cloud(
        self, audio_bytes: bytes, filename: str, language: str
    ) -> tuple[str, str | None, float | None]:
        url = f"{SETTINGS.STT_BASE_URL.rstrip('/')}/audio/transcriptions"
        headers = {}
        if SETTINGS.STT_API_KEY:
            headers["authorization"] = f"Bearer {SETTINGS.STT_API_KEY}"
        data = {"model": SETTINGS.STT_MODEL, "response_format": "json"}
        if language:
            data["language"] = language  # ISO-639-1 hint, not a constraint
        resp = httpx.post(
            url,
            headers=headers,
            data=data,
            files={"file": (filename, audio_bytes, "audio/wav")},
            timeout=UTTERANCE_STT_TIMEOUT_S,
        )
        if resp.status_code >= 400:
            raise ValueError(f"Transcription backend failed ({resp.status_code}): {resp.text[:200]}")
        body = resp.json()
        return (body.get("text") or ""), body.get("language"), None

    def _utterance_text_local(
        self, audio_bytes: bytes, language: str
    ) -> tuple[str, str | None, float | None]:
        whisper = self._load_whisper()
        with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
            tmp.write(audio_bytes)
            tmp.flush()
            segments, info = whisper.transcribe(tmp.name, language=language or None)
            text = " ".join((s.text or "").strip() for s in segments).strip()
        return text, getattr(info, "language", None), getattr(info, "language_probability", None)

    def _new_speaker_labeler(self, meeting_id: int, file_id: int) -> "_SpeakerLabeler":
        """A labeler that allocates the same display names _persist_segments would,
        so the streaming path can label a segment before anything is written.

        Speakers only this file's current transcript references are excluded from
        the numbering: persistence deletes them first, so they are not names this
        run has to avoid."""
        with Session(engine) as session:
            speakers = session.exec(
                select(MeetingSpeaker).where(MeetingSpeaker.meeting_id == meeting_id)
            ).all()
            surviving = [s.speaker_name for s in speakers if not _only_used_by_file(session, s.id, meeting_id, file_id)]
        return _SpeakerLabeler(_next_speaker_number(surviving))

    def _persist_segments(
        self,
        meeting_id: int,
        file_id: int,
        current_user_id: int,
        segments: list[SpeechSegment],
        labeler: "_SpeakerLabeler | None" = None,
    ) -> list[TranscriptSegmentDTO]:
        """Persist provider-neutral segments as MeetingRecording rows, creating one
        MeetingSpeaker per provider speaker. Re-transcribing a file replaces its
        previous transcript rows (and speakers no other file still references).

        `labeler` carries the display names a streaming caller has already sent to
        the client; without one the names are allocated here."""
        results: list[TranscriptSegmentDTO] = []
        with Session(engine) as session:
            old = session.exec(
                select(MeetingRecording).where(
                    MeetingRecording.meeting_id == meeting_id,
                    MeetingRecording.file_id == file_id,
                )
            ).all()
            old_speaker_ids = {r.speaker_id for r in old if r.speaker_id is not None}
            for r in old:
                session.delete(r)
            for sid in old_speaker_ids:
                still_used = session.exec(
                    select(MeetingRecording).where(
                        MeetingRecording.speaker_id == sid,
                        MeetingRecording.meeting_id == meeting_id,
                        MeetingRecording.file_id != file_id,
                    )
                ).first()
                if not still_used:
                    orphan = session.exec(
                        select(MeetingSpeaker).where(MeetingSpeaker.id == sid)
                    ).first()
                    if orphan:
                        session.delete(orphan)

            if labeler is None:
                existing_names = session.exec(
                    select(MeetingSpeaker.speaker_name).where(MeetingSpeaker.meeting_id == meeting_id)
                ).all()
                labeler = _SpeakerLabeler(_next_speaker_number(existing_names))

            # Provider speaker key -> row, scoped to this run only, so speakers
            # from different files never collide under one display name.
            speaker_rows: dict[str, MeetingSpeaker] = {}
            for seg in segments:
                speaker = None
                if seg.speaker_key is not None:
                    if seg.speaker_key not in speaker_rows:
                        speaker_rows[seg.speaker_key] = MeetingSpeaker(
                            speaker_name=labeler.label(seg.speaker_key),
                            meeting_id=meeting_id,
                            created_by_id=current_user_id,
                        )
                        session.add(speaker_rows[seg.speaker_key])
                        # Flush the speaker INSERT now so the row exists before any
                        # MeetingRecording references its id. There is no ORM
                        # relationship() between the two models, so the unit-of-work
                        # won't otherwise order the speaker INSERT before the
                        # recording INSERT within a single commit.
                        session.flush()
                    speaker = speaker_rows[seg.speaker_key]
                session.add(
                    MeetingRecording(
                        file_id=file_id,
                        meeting_id=meeting_id,
                        speaker_id=speaker.id if speaker else None,
                        start_time=str(seg.start_ms / 1000.0),
                        end_time=str(seg.end_ms / 1000.0),
                        text=seg.text,
                    )
                )
                results.append(
                    TranscriptSegmentDTO(
                        speaker_label=speaker.speaker_name if speaker else UNKNOWN_SPEAKER_LABEL,
                        speaker_name=_identified_name(speaker.speaker_name) if speaker else None,
                        start_ms=seg.start_ms,
                        end_ms=seg.end_ms,
                        text=seg.text,
                    )
                )
            session.commit()
        return results

    def get_transcript(self, meeting_id: str, current_user_id: int) -> list[TranscriptSegmentDTO]:
        """Stored, speaker-labeled transcript for a meeting, ordered as spoken."""
        with Session(engine) as session:
            rows = session.exec(
                select(MeetingRecording).where(
                    MeetingRecording.meeting_id == int(meeting_id),
                    MeetingRecording.text.is_not(None),
                )
            ).all()
            segments = [self._to_segment(session, r) for r in rows]
        segments.sort(key=lambda s: s.start_ms)
        return segments

    # ----- Helpers ---------------------------------------------------------

    def _transcript_text(self, meeting_id: str) -> str:
        """Build a 'Speaker: text' transcript from stored segments."""
        segments = self.get_transcript(meeting_id, 0)
        return "\n".join(f"{s.speaker_label}: {s.text}" for s in segments)

    def _to_segment(self, session: Session, recording: MeetingRecording) -> TranscriptSegmentDTO:
        speaker = None
        if recording.speaker_id is not None:
            speaker = session.exec(
                select(MeetingSpeaker).where(MeetingSpeaker.id == recording.speaker_id)
            ).first()
        label = speaker.speaker_name if speaker else UNKNOWN_SPEAKER_LABEL
        return TranscriptSegmentDTO(
            speaker_label=label,
            speaker_name=_identified_name(speaker.speaker_name) if speaker else None,
            start_ms=int(float(recording.start_time or 0) * 1000),
            end_ms=int(float(recording.end_time or 0) * 1000),
            text=recording.text or "",
        )

    def _load_whisper(self):
        if self._whisper is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as e:
                raise ValueError(
                    "Transcription requires faster-whisper on the server. "
                    "Install it with `uv add faster-whisper`."
                ) from e
            self._whisper = WhisperModel(SETTINGS.WHISPER_MODEL)
        return self._whisper


def _with_heartbeat(work, heartbeat):
    """Run a blocking call on a worker thread, yielding `heartbeat()` every
    STREAM_HEARTBEAT_S until it finishes, and return its result.

    Used with `yield from` inside the transcription stream. Every stage that can
    run for minutes without producing an event needs this: an idle connection is
    closed by nginx and AWS ALB after 60 s by default, and a stream that dies
    without its `done` event is indistinguishable from a real failure.
    """
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        future = pool.submit(work)
        while True:
            try:
                return future.result(timeout=STREAM_HEARTBEAT_S)
            except concurrent.futures.TimeoutError:
                yield heartbeat()
    finally:
        # Never wait: on a client disconnect this runs from GeneratorExit, and a
        # still-running job would otherwise block for minutes.
        pool.shutdown(wait=False, cancel_futures=True)


def _audio_duration_ms(path: str) -> int | None:
    """Length of a local audio file, or None when it can't be read cheaply.

    Taken from the WAV header where possible — the desktop uploads 16-bit PCM
    WAV — and otherwise from torchaudio, already installed for diarization, which
    covers the compressed formats the file picker allows. Neither decodes the
    audio, so this stays cheap on a multi-gigabyte recording.
    """
    with contextlib.suppress(Exception):
        with contextlib.closing(wave.open(path, "rb")) as wav:
            if wav.getframerate():
                return int(wav.getnframes() / wav.getframerate() * 1000)
    with contextlib.suppress(Exception):
        import torchaudio

        info = torchaudio.info(path)
        if info.sample_rate:
            return int(info.num_frames / info.sample_rate * 1000)
    return None


def _identified_name(speaker_name: str | None) -> str | None:
    """A speaker's actual name, or None when it is just the auto-assigned
    "Speaker N" placeholder.

    `speaker_label` already carries that placeholder, so repeating it in
    `speaker_name` would claim an identification the pipeline never made — a
    client could not tell "the server knows who this is" from "nobody named this
    speaker yet".
    """
    if not speaker_name or speaker_name == UNKNOWN_SPEAKER_LABEL:
        return None
    if re.fullmatch(r"Speaker \d+", speaker_name):
        return None
    return speaker_name


class _SpeakerLabeler:
    """Allocates "Speaker N" display names to provider speaker keys in
    first-appearance order, starting at `start_number`. Streaming and persistence
    share one instance so a segment keeps the label the client already saw."""

    def __init__(self, start_number: int):
        self._next = start_number
        self._labels: dict[str, str] = {}

    def label(self, speaker_key: str) -> str:
        if speaker_key not in self._labels:
            self._labels[speaker_key] = f"Speaker {self._next}"
            self._next += 1
        return self._labels[speaker_key]


def _only_used_by_file(session: Session, speaker_id: int, meeting_id: int, file_id: int) -> bool:
    """Whether every recording referencing this speaker belongs to `file_id` — the
    speakers re-transcribing that file would orphan and delete."""
    used_by_file = session.exec(
        select(MeetingRecording).where(
            MeetingRecording.speaker_id == speaker_id,
            MeetingRecording.meeting_id == meeting_id,
            MeetingRecording.file_id == file_id,
        )
    ).first()
    if not used_by_file:
        return False
    used_elsewhere = session.exec(
        select(MeetingRecording).where(
            MeetingRecording.speaker_id == speaker_id,
            MeetingRecording.meeting_id == meeting_id,
            MeetingRecording.file_id != file_id,
        )
    ).first()
    return used_elsewhere is None


def _status(stage: str, backend: str | None = None) -> dict:
    return TranscriptStreamStatusDTO(stage=stage, backend=backend).model_dump(by_alias=True)


def _progress(processed_ms: int | None, total_ms: int | None, elapsed_ms: int) -> dict:
    return TranscriptProgressDTO(
        processed_ms=processed_ms, total_ms=total_ms, elapsed_ms=elapsed_ms
    ).model_dump(by_alias=True)


def _wav_duration_ms(audio_bytes: bytes) -> int:
    """Duration of a PCM WAV from its header, without decoding samples. Raises
    ValueError on anything that isn't a readable WAV."""
    try:
        with contextlib.closing(wave.open(io.BytesIO(audio_bytes), "rb")) as wav:
            frames = wav.getnframes()
            rate = wav.getframerate()
    except (wave.Error, EOFError) as e:
        raise ValueError("Audio must be a valid WAV file.") from e
    if not rate:
        raise ValueError("Audio must be a valid WAV file.")
    return int(frames / rate * 1000)


def _best_speaker_label(turns: list[tuple[str, float, float]], start: float, end: float) -> str | None:
    """The diarization speaker label whose turn overlaps [start, end] the most,
    or None when nothing overlaps."""
    best, best_overlap = None, 0.0
    for label, s, e in turns:
        overlap = max(0.0, min(end, e) - max(start, s))
        if overlap > best_overlap:
            best_overlap, best = overlap, label
    return best


def _next_speaker_number(existing_names: list[str]) -> int:
    """1 + the highest N among existing "Speaker N" names (1 when there are none),
    so new speakers never reuse a display name already taken in the meeting."""
    highest = 0
    for name in existing_names:
        match = re.fullmatch(r"Speaker (\d+)", name or "")
        if match:
            highest = max(highest, int(match.group(1)))
    return highest + 1


def _parse_summary(raw: str) -> dict:
    """Leniently extract the JSON object from the model reply; fall back to using
    the whole text as the summary."""
    slice_ = None
    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        slice_ = raw[start : end + 1]
    if slice_:
        try:
            v = json.loads(slice_)
            summary = (v.get("summary") or "").strip()
            key_points = [str(x) for x in (v.get("key_points") or [])]
            action_items = [str(x) for x in (v.get("action_items") or [])]
            if summary or key_points or action_items:
                return {"summary": summary, "key_points": key_points, "action_items": action_items}
        except json.JSONDecodeError:
            pass
    return {"summary": raw.strip(), "key_points": [], "action_items": []}
