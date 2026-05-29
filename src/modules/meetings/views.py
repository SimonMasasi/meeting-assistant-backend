from fastapi import APIRouter, Depends
from src.modules.meetings.models import Meeting  , MeetingRecording
from src.modules.auth.models import User
from src.shared.dtos import  ListResponse ,SingleResponse
from fastapi import Query
from typing import Annotated
from .dtos import MeetingInputDTO , MeetingFilteringInputDTO, MeetingRecordingFilteringInputDTO , MeetingRecordingInputDto
from .services import MeetingService
from src.shared.dependencies import get_current_user


meeting_router = APIRouter(prefix="/meetings", tags=["meetings"])
meeting_service = MeetingService()


@meeting_router.post("/create_meeting")
def create_meeting(meeting_input: MeetingInputDTO, current_user: User = Depends(get_current_user)) -> SingleResponse[Meeting]:
    return meeting_service.create_meeting(meeting_input, current_user.id)

@meeting_router.get("/get_meetings")
def get_meetings(params: Annotated[MeetingFilteringInputDTO, Query()], current_user: User = Depends(get_current_user)) -> ListResponse[Meeting]:
    return meeting_service.get_meetings(params, current_user.id)


@meeting_router.post("/add_meeting_recording")
def add_meeting_recording(input: MeetingRecordingInputDto, current_user: User = Depends(get_current_user)) -> SingleResponse[list[MeetingRecording]]:
    return meeting_service.add_meeting_recording(input, current_user.id)

@meeting_router.get("/get_meeting_recordings")
def get_meeting_recordings(params: Annotated[MeetingRecordingFilteringInputDTO, Query()]) -> ListResponse[MeetingRecording]:
    return meeting_service.get_meeting_recordings(params)