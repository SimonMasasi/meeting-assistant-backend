from sqlmodel import Field
from src.shared.base_model import BaseModel
from pydantic import computed_field


from datetime import datetime


class Meeting(BaseModel, table=True):
    __tablename__ = "meetings"

    title: str
    description: str | None = None
    start_time: datetime = Field(default_factory=datetime.now)
    end_time: datetime| None = None
    created_by_id: int = Field(foreign_key="users.id")
        
    @computed_field
    @property
    def duration_minutes(self) -> int | None:
        if self.end_time is None:
            return None
        return int((self.end_time - self.start_time).total_seconds() / 60)
    
    
    
class MeetingSpeaker(BaseModel, table=True):
    __tablename__ = "meeting_speakers"

    speaker_name: str = Field(..., min_length=1)
    
    meeting_id: int = Field(foreign_key="meetings.id")
    created_by_id: int = Field(foreign_key="users.id")
    
    
class MeetingRecording(BaseModel, table=True):
    __tablename__ = "meeting_recordings"

    file_id: int = Field(foreign_key="uploaded_files.id")
    meeting_id: int = Field(foreign_key="meetings.id")
    speaker_id: int | None = Field(foreign_key="meeting_speakers.id", default=None)