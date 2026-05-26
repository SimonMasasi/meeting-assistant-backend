import re
from fastapi import APIRouter  , UploadFile , HTTPException
from fastapi.responses import StreamingResponse 
from .services import UploadService
from src.shared.dtos import SingleResponse
from .models import UploadedFile


uploads_router = APIRouter(prefix="/uploads", tags=["uploads"])
upload_service = UploadService()


@uploads_router.post("/upload-file")
def upload_file(file:UploadFile) -> SingleResponse[UploadedFile]:
    return upload_service.upload_file(file)


@uploads_router.get("/get-file/{file_id}")
def get_file(file_id: str):
    success, message, file_bytes, file_metadata = upload_service.get_file(file_id)

    if not success:
        raise HTTPException(status_code=400, detail=message)

    safe_filename = re.sub(r'[\r\n"\\]', '_', file_metadata.filename)
    return StreamingResponse(content=iter([file_bytes]), media_type=file_metadata.mimetype, headers={"Content-Disposition": f'attachment; filename="{safe_filename}"'})
