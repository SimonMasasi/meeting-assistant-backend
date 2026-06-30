from sqlmodel import Field , select , Session
from sqlalchemy import BigInteger
from src.shared.base_model import BaseModel
from pydantic import computed_field

from src.modules.uploads.models import UploadedFile
from src.shared.database import engine 



from datetime import datetime


class Meeting(BaseModel, table=True):
    __tablename__ = "meetings"

    title: str
    description: str | None = None
    start_time: datetime = Field(default_factory=datetime.now)
    end_time: datetime| None = None
    created_by_id: int = Field(foreign_key="users.id" , sa_type=BigInteger() , exclude=True)
    # Opaque JSON bag of the desktop client's presentation-only fields (status,
    # source, tags, host, date/time, views, attendees, durationLabel, language,
    # createdAt). The backend stores it verbatim so cloud-mode meetings round-trip
    # losslessly; title/description remain first-class columns.
    client_meta: str | None = None
    # Cached AI summary (SummaryDTO as JSON), produced by cloud summarization. Lets
    # the client read a generated summary back without re-billing the LLM.
    summary_json: str | None = None
        
    @computed_field
    @property
    def duration_minutes(self) -> int | None:
        if self.end_time is None:
            return None
        return int((self.end_time - self.start_time).total_seconds() / 60)
    
    
    
class MeetingSpeaker(BaseModel, table=True):
    __tablename__ = "meeting_speakers"

    speaker_name: str = Field(..., min_length=1)
    
    meeting_id: int = Field(foreign_key="meetings.id" , sa_type=BigInteger() , exclude=True)
    created_by_id: int = Field(foreign_key="users.id" , sa_type=BigInteger() , exclude=True)
    speaker_embeddings: str | None  = Field(default=None , exclude=True)

    
    
class MeetingRecording(BaseModel, table=True):
    __tablename__ = "meeting_recordings"

    file_id: int = Field(foreign_key="uploaded_files.id" , sa_type=BigInteger() , exclude=True)
    meeting_id: int = Field(foreign_key="meetings.id" , sa_type=BigInteger() , exclude=True)
    speaker_id: int | None = Field(foreign_key="meeting_speakers.id", sa_type=BigInteger() , default=None , exclude=True)

    start_time: str | None = None
    end_time: str | None = None
    # Transcribed text for this diarized segment (populated by cloud transcription).
    text: str | None = None


    @computed_field
    @property
    def file(self) -> UploadedFile | None:
        with Session(engine) as session:
            return session.exec(select(UploadedFile).where(UploadedFile.id == self.file_id)).first()
        
    @computed_field
    @property
    def speaker(self) -> MeetingSpeaker | None:
        if self.speaker_id is None:
            return None
        with Session(engine) as session:
            return session.exec(select(MeetingSpeaker).where(MeetingSpeaker.id == self.speaker_id)).first()
