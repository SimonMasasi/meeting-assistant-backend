from src.shared.base_model import CamelCaseModel


class TranscribeInputDTO(CamelCaseModel):
    # Id of the already-uploaded audio file (see /uploads/upload-file).
    file_id: str


class TranscriptSegmentDTO(CamelCaseModel):
    # The speaker's display label, always set: an actual name once someone is
    # identified, otherwise the auto-assigned "Speaker N".
    speaker_label: str
    # Only an actual identification — None while the speaker is still just
    # "Speaker N", so a client can tell the two apart.
    speaker_name: str | None = None
    start_ms: int
    end_ms: int
    text: str


# ----- /inference/transcribe-stream event payloads -------------------------
# One class per SSE event type. FastAPI cannot type an event stream, so these
# exist to build the payloads (dumped with by_alias=True) and to document the
# contract in one place.


class TranscriptStreamStatusDTO(CamelCaseModel):
    # "downloading" | "diarizing" | "transcribing" | "saving"
    stage: str
    # "soniox" | "local", or None before a backend has been chosen.
    backend: str | None = None


class TranscriptProgressDTO(CamelCaseModel):
    # How far into the audio the transcript has reached. None while no position is
    # known — during the download and diarization stages, and for the whole of a
    # Soniox run, which reports no partials. Treat those as indeterminate.
    processed_ms: int | None = None
    # The audio's length, known from its header as soon as the file is local, so
    # it is usually set even when processed_ms is not.
    total_ms: int | None = None
    elapsed_ms: int = 0


class TranscriptSegmentEventDTO(TranscriptSegmentDTO):
    # Position in the stream, so a client can render without tracking its own count.
    index: int


class TranscriptStreamDoneDTO(CamelCaseModel):
    segment_count: int


class TranscriptStreamErrorDTO(CamelCaseModel):
    message: str


class UtteranceTranscriptDTO(CamelCaseModel):
    # Trimmed transcript for one live utterance; "" for non-speech (not an error).
    text: str
    duration_ms: int | None = None
    language: str | None = None
    confidence: float | None = None


class SummaryDTO(CamelCaseModel):
    summary: str
    key_points: list[str]
    action_items: list[str]
    # "provider:model" that produced this summary, for display.
    model: str
