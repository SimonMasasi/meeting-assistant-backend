from src.modules.meetings.models import MeetingSpeaker
from src.shared.database import engine 
from sqlmodel import Session, select  

class SpeakerDiarizationService:
    def __init__(self):
        pass
    
    def diarize(self, audio_bytes: bytes , meeting_id: int , current_user_id: int) -> list[tuple[MeetingSpeaker, str, str]]:
        # Placeholder implementation for speaker diarization
        # In a real implementation, this would process the audio file and return speaker segments

        hardcoded_speakers = [
            {"speaker_name": "Speaker 1", "start_time": 0, "end_time": 30 , "speaker_embeddings": "embedding1"},
            {"speaker_name": "Speaker 2", "start_time": 30, "end_time": 60, "speaker_embeddings": "embedding2"},
        ]

        speakers: list[tuple[MeetingSpeaker, str, str]] = []

        for speaker in hardcoded_speakers:
            with Session(engine) as session:
                existing_speaker = session.exec(
                    select(MeetingSpeaker).where(
                        MeetingSpeaker.speaker_name == speaker["speaker_name"],
                        MeetingSpeaker.meeting_id == meeting_id
                    )
                ).first()

                if existing_speaker:
                    speakers.append((existing_speaker, speaker["start_time"], speaker["end_time"]))
                    continue

                new_speaker = MeetingSpeaker(
                    speaker_name=speaker["speaker_name"],
                    speaker_embeddings=speaker["speaker_embeddings"],
                    meeting_id=meeting_id,
                    created_by_id=current_user_id
                )
                session.add(new_speaker)
                session.commit()
                session.refresh(new_speaker)
                speakers.append((new_speaker, speaker["start_time"], speaker["end_time"]))


        return speakers