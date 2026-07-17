from src.shared.base_model import CamelCaseModel


class TranscribeInputDTO(CamelCaseModel):
    # Id of the already-uploaded audio file (see /uploads/upload-file).
    file_id: str


class TranscriptSegmentDTO(CamelCaseModel):
    speaker_label: str
    speaker_name: str | None = None
    start_ms: int
    end_ms: int
    text: str


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
