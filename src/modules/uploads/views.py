import re
from fastapi import APIRouter  , UploadFile , HTTPException, Depends
from fastapi.responses import StreamingResponse 
from starlette.background import BackgroundTask
from .services import UploadService
from src.shared.dtos import SingleResponse
from .models import UploadedFile
from src.shared.dependencies import get_current_user
from src.utils.helper_functions import iter_file_chunks


uploads_router = APIRouter(prefix="/uploads", tags=["uploads"])
upload_service = UploadService()




@uploads_router.post("/upload-file", dependencies=[Depends(get_current_user)])
def upload_file(file:UploadFile) -> SingleResponse[UploadedFile]:
    return upload_service.upload_file(file)


@uploads_router.get("/get-file/{file_id}")
def get_file(file_id: str):
    success, message, file_stream, file_metadata = upload_service.get_file(file_id)
    if not success:
        raise HTTPException(status_code=400, detail=message)

    safe_filename = re.sub(r'[\r\n"\\]', '_', file_metadata.filename)
    return StreamingResponse(
        content=iter_file_chunks(file_stream),
        media_type=file_metadata.mimetype,
        headers={"Content-Disposition": f'attachment; filename="{safe_filename}"'},
        background=BackgroundTask(file_stream.close),
    )
