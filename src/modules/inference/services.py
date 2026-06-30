"""Cloud inference: transcription (Whisper ASR + pyannote diarization) and
summarization (any OpenAI-compatible chat endpoint).

Summarization is dependency-light (httpx) and configured purely via env
(`LLM_BASE_URL`/`LLM_API_KEY`/`LLM_MODEL`). Transcription additionally needs
`faster-whisper` installed on the server (`uv add faster-whisper`); it is
imported lazily so the rest of the API runs without it.
"""
import json
import logging
import tempfile

import httpx
from sqlmodel import Session, select

from config import SETTINGS
from src.shared.database import engine
from src.modules.meetings.models import Meeting, MeetingRecording, MeetingSpeaker
from src.modules.uploads.services import UploadService
from src.utils.audio.speaker_diarization import SpeakerDiarizationService
from .dtos import SummaryDTO, TranscriptSegmentDTO

logger = logging.getLogger(__name__)

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
            "max_tokens": 1024,
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

    # ----- Transcription (Whisper + diarization) ---------------------------

    def transcribe(self, meeting_id: str, file_id: str, current_user_id: int) -> list[TranscriptSegmentDTO]:
        """Diarize + transcribe an uploaded audio file, persisting one segment per
        ASR line (with the best-overlapping speaker) and returning them."""
        ok, message, file_stream, _ = self.upload_service.get_file(file_id)
        if not ok:
            raise ValueError(message)
        audio_bytes = file_stream.read() if hasattr(file_stream, "read") else bytes(file_stream)

        # Speaker timeline (creates/reuses MeetingSpeaker rows).
        speakers = self.diarization_service.diarize(audio_bytes, int(meeting_id), current_user_id)

        # ASR over the whole file via faster-whisper (decodes through ffmpeg).
        whisper = self._load_whisper()
        with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
            tmp.write(audio_bytes)
            tmp.flush()
            asr_segments, _info = whisper.transcribe(tmp.name)
            asr = [(float(s.start), float(s.end), (s.text or "").strip()) for s in asr_segments]

        results: list[TranscriptSegmentDTO] = []
        with Session(engine) as session:
            for start, end, text in asr:
                if not text:
                    continue
                speaker = _best_speaker(speakers, start, end)
                recording = MeetingRecording(
                    file_id=int(file_id),
                    meeting_id=int(meeting_id),
                    speaker_id=speaker.id if speaker else None,
                    start_time=str(start),
                    end_time=str(end),
                    text=text,
                )
                session.add(recording)
                results.append(
                    TranscriptSegmentDTO(
                        speaker_label=speaker.speaker_name if speaker else "Speaker 1",
                        speaker_name=speaker.speaker_name if speaker else None,
                        start_ms=int(start * 1000),
                        end_ms=int(end * 1000),
                        text=text,
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
        label = speaker.speaker_name if speaker else "Speaker 1"
        return TranscriptSegmentDTO(
            speaker_label=label,
            speaker_name=speaker.speaker_name if speaker else None,
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


def _best_speaker(speakers: list[tuple[MeetingSpeaker, str, str]], start: float, end: float):
    """The diarization speaker whose interval overlaps [start, end] the most."""
    best, best_overlap = None, 0.0
    for speaker, s, e in speakers:
        overlap = max(0.0, min(end, float(e)) - max(start, float(s)))
        if overlap > best_overlap:
            best_overlap, best = overlap, speaker
    return best


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
