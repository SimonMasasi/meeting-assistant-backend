from pydantic import Field
from src.shared.base_model import CamelCaseModel
from src.shared.dtos import BaseFilteringInput


from datetime import datetime


class MeetingInputDTO(CamelCaseModel):
    title: str  = Field(..., min_length=3, max_length=100)
    description: str | None = None
    # Opaque JSON blob of the desktop client's presentation fields (see Meeting model).
    client_meta: str | None = None


class MeetingUpdateDTO(CamelCaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=100)
    description: str | None = None
    client_meta: str | None = None


class MeetingFilteringInputDTO(BaseFilteringInput):
    pass


class MeetingRecordingInputDto(CamelCaseModel):
    meeting_id: str
    file_id: str
    start_time: str
    end_time: str


class MeetingRecordingFilteringInputDTO(BaseFilteringInput):
    meeting_id: str