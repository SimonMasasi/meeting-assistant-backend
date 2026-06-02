from fastapi import  UploadFile
from src.utils.uploads.uploads_manager import UploadsManager
from .models import UploadedFile
from src.shared.dtos import SingleResponse, ResponseObjects

from src.shared.database import engine 
from sqlmodel import Session, select 
from sqlalchemy.exc import IntegrityError


MAX_UPLOAD_SIZE_BYTES = 20 * 1024 * 1024

class UploadService:
    def __init__(self):
        self.upload_provider = UploadsManager()

    def upload_file(self, file: UploadFile) -> SingleResponse[UploadedFile]:
        if not file.filename:
            return SingleResponse(data=None , response=ResponseObjects.get_response(id=2 , message="Filename is required"))

        file.file.seek(0, 2)
        file_size = file.file.tell()
        file.file.seek(0)
        if file_size > MAX_UPLOAD_SIZE_BYTES:
            return SingleResponse(data=None , response=ResponseObjects.get_response(id=2 , message="File exceeds 20MB limit"))

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
        