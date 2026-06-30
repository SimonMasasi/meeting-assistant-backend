from fastapi import APIRouter, Depends
from src.modules.meetings.models import Meeting  , MeetingRecording
from src.modules.auth.models import User
from src.shared.dtos import  ListResponse ,SingleResponse
from fastapi import Query
from typing import Annotated
from .dtos import MeetingInputDTO , MeetingUpdateDTO , MeetingFilteringInputDTO, MeetingRecordingFilteringInputDTO , MeetingRecordingInputDto
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


# Path-parameter routes are declared last so they don't shadow the literal
# `/meetings/get_meetings` and `/meetings/get_meeting_recordings` routes above.

@meeting_router.get("/{meeting_id}")
def get_meeting(meeting_id: str, current_user: User = Depends(get_current_user)) -> SingleResponse[Meeting]:
    return meeting_service.get_meeting(meeting_id, current_user.id)


@meeting_router.put("/{meeting_id}")
def update_meeting(meeting_id: str, update_input: MeetingUpdateDTO, current_user: User = Depends(get_current_user)) -> SingleResponse[Meeting]:
    return meeting_service.update_meeting(meeting_id, update_input, current_user.id)


@meeting_router.delete("/{meeting_id}")
def delete_meeting(meeting_id: str, current_user: User = Depends(get_current_user)) -> SingleResponse[None]:
    return meeting_service.delete_meeting(meeting_id, current_user.id)