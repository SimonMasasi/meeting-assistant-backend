from sqlmodel import Session, select

from src.modules.meetings.models import MeetingSpeaker
from src.shared.database import engine


class SpeakerDiarizationService:
    def __init__(self):
        # Lazy: constructing PyNoteDiarization downloads the pyannote model and
        # needs HUGGINGFACE_TOKEN, which a Soniox-only deployment doesn't have.
        self._diarizer = None

    def _get_diarizer(self):
        if self._diarizer is None:
            from .diarization.pynote import PyNoteDiarization

            self._diarizer = PyNoteDiarization()
        return self._diarizer

    def diarize_turns(self, audio: bytes | str) -> list[tuple[str, float, float]]:
        """Raw speaker turns as (provider_label, start_s, end_s). No DB access.

        `audio` is either the bytes or a path to a local file; pass a path for
        large recordings so nothing multi-gigabyte is held in memory."""
        return [
            (t["speaker"], t["start"], t["end"])
            for t in self._get_diarizer().diarize(audio)
        ]

    def diarize(
        self, audio: bytes | str, meeting_id: int, current_user_id: int
    ) -> list[tuple[MeetingSpeaker, float, float]]:
        """Legacy shape kept for MeetingService.add_meeting_recording: dedupes or
        creates MeetingSpeaker rows keyed by (speaker_name, meeting_id). Note this
        merges same-named speakers across different files in one meeting; the
        inference transcription path uses diarize_turns() instead."""
        turns = self.diarize_turns(audio)
        by_label: dict[str, MeetingSpeaker] = {}
        results: list[tuple[MeetingSpeaker, float, float]] = []
        with Session(engine) as session:
            for label, start, end in turns:
                if label not in by_label:
                    existing = session.exec(
                        select(MeetingSpeaker).where(
                            MeetingSpeaker.speaker_name == label,
                            MeetingSpeaker.meeting_id == meeting_id,
                        )
                    ).first()
                    speaker = existing or MeetingSpeaker(
                        speaker_name=label,
                        meeting_id=meeting_id,
                        created_by_id=current_user_id,
                    )
                    if existing is None:
                        session.add(speaker)
                    by_label[label] = speaker
                results.append((by_label[label], start, end))
            session.commit()
            for speaker in by_label.values():
                session.refresh(speaker)
        return results
