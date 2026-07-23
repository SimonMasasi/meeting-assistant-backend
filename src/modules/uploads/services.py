import contextlib
import logging
import os

from fastapi import  UploadFile
from src.utils.uploads.uploads_manager import UploadsManager
from .models import TusUpload, UploadedFile
from src.shared.dtos import SingleResponse, ResponseObjects

from config import SETTINGS
from src.shared.database import engine
from sqlmodel import Session, select
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)


def _size_limit_label(size_bytes: int) -> str:
    return f"{size_bytes // (1024 * 1024)}MB"


class UploadService:
    def __init__(self):
        self.upload_provider = UploadsManager()

    def upload_file(self, file: UploadFile) -> SingleResponse[UploadedFile]:
        if not file.filename:
            return SingleResponse(data=None , response=ResponseObjects.get_response(id=2 , message="Filename is required"))

        file.file.seek(0, 2)
        file_size = file.file.tell()
        file.file.seek(0)
        if file_size > SETTINGS.MAX_UPLOAD_SIZE_BYTES:
            # This path buffers the whole body in memory, hence the modest cap.
            # Larger files go through the resumable tus endpoint instead.
            limit = _size_limit_label(SETTINGS.MAX_UPLOAD_SIZE_BYTES)
            return SingleResponse(data=None , response=ResponseObjects.get_response(id=2 , message=f"File exceeds {limit} limit. Use the resumable /uploads/tus endpoint for larger files."))

        file_bytes = file.file.read()
        file_mimetype = self.upload_provider.get_file_mimetype(file_bytes)

        object_name = file.filename
        
        file_hash = self.upload_provider.calculate_file_hash(file_bytes)
        with Session(engine) as session:
            existing_file = session.exec(select(UploadedFile).where(UploadedFile.file_hash == file_hash)).first()
            if existing_file:
                return SingleResponse(data=existing_file , response=ResponseObjects.get_response(id=1 , message="File already exists, returning existing file metadata"))
        
        success , message  , file_path =  self.upload_provider.upload_file(file_bytes, object_name)
        if not success:
            return SingleResponse(data=None , response=ResponseObjects.get_response(id=2 , message=message))
        
        file_size = self.upload_provider.calculate_file_size(file_bytes)
        
        
        with Session(engine) as session:
            #Save file metadata to database
            uploaded_file = UploadedFile(
                filename=file.filename,
                size=file_size,
                mimetype=file_mimetype,
                file_path=file_path,
                file_hash=file_hash,
                file_type=self.upload_provider.classify_file_type_to_file_enum(file.filename),
                content_type=file.content_type,
                
            )
            session.add(uploaded_file)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                existing_file = session.exec(select(UploadedFile).where(UploadedFile.file_hash == file_hash)).first()
                if existing_file:
                    return SingleResponse(data=existing_file , response=ResponseObjects.get_response(id=1 , message="File already exists, returning existing file metadata"))
                return SingleResponse(data=None , response=ResponseObjects.get_response(id=2 , message="Unable to save file metadata"))
            session.refresh(uploaded_file)
        
        return SingleResponse(data=uploaded_file , response=ResponseObjects.get_response(id=1 , message="File uploaded successfully"))
    
    
    def get_file(self, file_id: str):
        with Session(engine) as session:
            file_metadata = session.exec(select(UploadedFile).where(UploadedFile.id == file_id)).first()
            if not file_metadata:
                return False , "File metadata not found" , None , None
        
        file_stream = self.upload_provider.get_file_stream(file_metadata.file_path)
        if file_stream is None:
            return False , "File not found in storage" , None , None

        return True , "File retrieved successfully" , file_stream , file_metadata

    def get_file_metadata(self, file_id: str) -> UploadedFile | None:
        with Session(engine) as session:
            return session.exec(select(UploadedFile).where(UploadedFile.id == file_id)).first()

    def download_to_path(self, file_id: str, dest_path: str):
        """Copy a stored file to a local path without holding it in memory.

        Returns (success, message, file_metadata). Callers that need to work on a
        whole audio file (transcription, diarization) use this instead of
        get_file() so a multi-gigabyte recording never becomes a bytes object.
        """
        with Session(engine) as session:
            file_metadata = session.exec(select(UploadedFile).where(UploadedFile.id == file_id)).first()
            if not file_metadata:
                return False , "File metadata not found" , None

        if not self.upload_provider.get_file_to_path(file_metadata.file_path, dest_path):
            return False , "File not found in storage" , None

        return True , "File retrieved successfully" , file_metadata

    def finalize_tus_upload(self, tus_upload: TusUpload) -> SingleResponse[UploadedFile]:
        """Turn a completed tus buffer into an UploadedFile row.

        Mirrors upload_file() but never materializes the file: the hash, the
        mimetype and the store are all done by streaming from the buffer on disk.
        """
        temp_path = tus_upload.temp_path

        with open(temp_path, 'rb') as buffered:
            file_hash = self.upload_provider.hash_stream(buffered)

            with Session(engine) as session:
                existing_file = session.exec(select(UploadedFile).where(UploadedFile.file_hash == file_hash)).first()
                if existing_file:
                    self._discard_tus_buffer(temp_path)
                    self._mark_tus_complete(tus_upload, existing_file.id)
                    return SingleResponse(data=existing_file , response=ResponseObjects.get_response(id=1 , message="File already exists, returning existing file metadata"))

            file_mimetype = self.upload_provider.mimetype_of_head(buffered)
            file_size = os.path.getsize(temp_path)

            success , message , file_path = self.upload_provider.upload_stream(
                buffered, tus_upload.filename, file_size, source_path=temp_path
            )

        if not success:
            return SingleResponse(data=None , response=ResponseObjects.get_response(id=2 , message=message))

        # upload_stream may have consumed the buffer by moving it; drop whatever remains.
        self._discard_tus_buffer(temp_path)

        with Session(engine) as session:
            uploaded_file = UploadedFile(
                filename=tus_upload.filename,
                size=file_size,
                mimetype=file_mimetype,
                file_path=file_path,
                file_hash=file_hash,
                file_type=self.upload_provider.classify_file_type_to_file_enum(tus_upload.filename),
                content_type=tus_upload.content_type or file_mimetype,
            )
            session.add(uploaded_file)
            try:
                session.commit()
            except IntegrityError:
                # Another upload of identical content landed first.
                session.rollback()
                existing_file = session.exec(select(UploadedFile).where(UploadedFile.file_hash == file_hash)).first()
                if existing_file:
                    self._mark_tus_complete(tus_upload, existing_file.id)
                    return SingleResponse(data=existing_file , response=ResponseObjects.get_response(id=1 , message="File already exists, returning existing file metadata"))
                return SingleResponse(data=None , response=ResponseObjects.get_response(id=2 , message="Unable to save file metadata"))
            session.refresh(uploaded_file)

        self._mark_tus_complete(tus_upload, uploaded_file.id)
        return SingleResponse(data=uploaded_file , response=ResponseObjects.get_response(id=1 , message="File uploaded successfully"))

    def _discard_tus_buffer(self, temp_path: str) -> None:
        with contextlib.suppress(OSError):
            os.remove(temp_path)

    def _mark_tus_complete(self, tus_upload: TusUpload, uploaded_file_id: int) -> None:
        tus_upload.uploaded_file_id = uploaded_file_id
        with Session(engine) as session:
            row = session.get(TusUpload, tus_upload.id)
            if row:
                row.uploaded_file_id = uploaded_file_id
                session.add(row)
                session.commit()
        