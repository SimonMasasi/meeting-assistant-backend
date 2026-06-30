from fastapi import APIRouter, Depends

from src.modules.auth.models import User
from src.shared.dependencies import get_current_user
from src.shared.dtos import ListResponse, ResponseObjects, SingleResponse
from .dtos import SummaryDTO, TranscribeInputDTO, TranscriptSegmentDTO
from .services import InferenceService

inference_router = APIRouter(prefix="/inference", tags=["inference"])
inference_service = InferenceService()


@inference_router.post("/transcribe/{meeting_id}")
def transcribe(meeting_id: str, input: TranscribeInputDTO, current_user: User = Depends(get_current_user)) -> ListResponse[TranscriptSegmentDTO]:
    try:
        segments = inference_service.transcribe(meeting_id, input.file_id, current_user.id)
    except Exception as e:
        return ListResponse(response=ResponseObjects.get_response(3, str(e)), data=None)
    return ListResponse(response=ResponseObjects.get_response(1), data=segments)


@inference_router.get("/transcript/{meeting_id}")
def get_transcript(meeting_id: str, current_user: User = Depends(get_current_user)) -> ListResponse[TranscriptSegmentDTO]:
    segments = inference_service.get_transcript(meeting_id, current_user.id)
    return ListResponse(response=ResponseObjects.get_response(1), data=segments)


@inference_router.post("/summarize/{meeting_id}")
def summarize(meeting_id: str, current_user: User = Depends(get_current_user)) -> SingleResponse[SummaryDTO]:
    try:
        dto = inference_service.summarize_meeting(meeting_id, current_user.id)
    except Exception as e:
        return SingleResponse(response=ResponseObjects.get_response(3, str(e)), data=None)
    return SingleResponse(response=ResponseObjects.get_response(1), data=dto)


@inference_router.get("/summary/{meeting_id}")
def get_summary(meeting_id: str, current_user: User = Depends(get_current_user)) -> SingleResponse[SummaryDTO]:
    dto = inference_service.get_summary(meeting_id, current_user.id)
    return SingleResponse(response=ResponseObjects.get_response(1), data=dto)
