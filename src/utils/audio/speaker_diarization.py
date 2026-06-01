from src.modules.meetings.models import MeetingSpeaker
from src.shared.database import engine 
from sqlmodel import Session, select  
from .diarization.pynote import PyNoteDiarization

class SpeakerDiarizationService:
    def __init__(self):
        self.diarizer = PyNoteDiarization()
    
    def diarize(self, audio_bytes: bytes , meeting_id: int , current_user_id: int) -> list[tuple[MeetingSpeaker, str, str]]:
        # Placeholder implementation for speaker diarization
        # In a real implementation, this would process the audio file and return speaker segments

        diarization_results = self.diarizer.diarize(audio_bytes)
        speakers: list[tuple[MeetingSpeaker, str, str]] = []

        for speaker in diarization_results:
            with Session(engine) as session:
                existing_speaker = session.exec(
                    select(MeetingSpeaker).where(
                        MeetingSpeaker.speaker_name == speaker["speaker"],
                        MeetingSpeaker.meeting_id == meeting_id
                    )
                ).first()

                if existing_speaker:
                    speakers.append((existing_speaker, speaker["start"], speaker["end"]))
                    continue

                new_speaker = MeetingSpeaker(
                    speaker_name=speaker["speaker"],
                    speaker_embeddings=speaker.get("speaker_embeddings", None),
                    meeting_id=meeting_id,
                    created_by_id=current_user_id
                )
                session.add(new_speaker)
                session.commit()
                session.refresh(new_speaker)
                speakers.append((new_speaker, speaker["start"], speaker["end"]))


        return speakers