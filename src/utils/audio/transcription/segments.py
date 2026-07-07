from dataclasses import dataclass


@dataclass
class SpeechSegment:
    """One speaker turn of transcribed speech, provider-neutral."""

    speaker_key: str | None  # provider-local speaker id ("1", "SPEAKER_00"); None = unknown
    start_ms: int
    end_ms: int
    text: str
