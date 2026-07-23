import logging

from fastapi import APIRouter, Depends, UploadFile
from fastapi.responses import StreamingResponse

from src.modules.auth.models import User
from src.shared.dependencies import get_current_user
from src.shared.dtos import ListResponse, ResponseObjects, SingleResponse
from src.utils.helper_functions import sse_event
from .dtos import SummaryDTO, TranscribeInputDTO, TranscriptSegmentDTO, UtteranceTranscriptDTO
from .services import InferenceService

logger = logging.getLogger(__name__)

inference_router = APIRouter(prefix="/inference", tags=["inference"])
inference_service = InferenceService()


@inference_router.post("/transcribe/{meeting_id}")
def transcribe(meeting_id: str, input: TranscribeInputDTO, current_user: User = Depends(get_current_user)) -> ListResponse[TranscriptSegmentDTO]:
    try:
        segments = inference_service.transcribe(meeting_id, input.file_id, current_user.id)
    except Exception as e:
        return ListResponse(response=ResponseObjects.get_response(3, str(e)), data=None)
    return ListResponse(response=ResponseObjects.get_response(1), data=segments)


@inference_router.post(
    "/transcribe-stream/{meeting_id}",
    responses={200: {"content": {"text/event-stream": {}}}},
)
def transcribe_stream(meeting_id: str, input: TranscribeInputDTO, current_user: User = Depends(get_current_user)):
    """The same work as /transcribe/{meeting_id}, streamed as server-sent events
    so a long recording shows a transcript while it is still being produced.

    Events: `status`, `progress`, `segment`, `done`, `error`. Since the response
    headers go out before the work starts, a failure cannot change the status
    code — it arrives as an `error` event, and a stream that ends without `done`
    must be treated as failed.

    Declared sync on purpose: the service layer blocks throughout, and Starlette
    iterates a sync generator in a worker thread, keeping the event loop free.
    """
    def events():
        try:
            for name, payload in inference_service.transcribe_iter(meeting_id, input.file_id, current_user.id):
                print("Streaming transcription event %s: %s", name, payload)
                yield sse_event(name, payload)
        except Exception as e:
            logger.exception("Streaming transcription failed for meeting %s", meeting_id)
            yield sse_event("error", {"message": str(e)})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Stop nginx buffering the response, which would defeat the streaming.
            "X-Accel-Buffering": "no",
        },
    )


@inference_router.post("/transcribe-utterance")
def transcribe_utterance(
    file: UploadFile,
    language: str = "en",
    current_user: User = Depends(get_current_user),
) -> SingleResponse[UtteranceTranscriptDTO]:
    """Live cloud-mode transcription of one short utterance. Stateless: writes
    nothing, safe to retry. Non-speech returns text "" with status true."""
    try:
        dto = inference_service.transcribe_utterance(file, language)
    except ValueError as e:
        return SingleResponse(response=ResponseObjects.get_response(2, str(e)), data=None)
    except Exception as e:
        return SingleResponse(response=ResponseObjects.get_response(3, str(e)), data=None)
    return SingleResponse(response=ResponseObjects.get_response(1, "Transcribed"), data=dto)


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
