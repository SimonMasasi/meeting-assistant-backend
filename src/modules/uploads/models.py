from sqlmodel import Field
from datetime import datetime
from src.shared.base_model import BaseModel
from src.shared.enums import FileTypeEnum


class UploadedFile(BaseModel, table=True):
    
    __tablename__ = "uploaded_files"

    created_at: datetime = Field(default_factory=datetime.now, exclude=True)
    updated_at: datetime = Field(default_factory=datetime.now, exclude=True)
    deleted_at: datetime | None = Field(default=None, exclude=True)

    filename: str
    content_type: str
    size: int
    file_path: str
    file_type: FileTypeEnum = Field(default=FileTypeEnum.OTHER)
    file_hash: str | None = Field(default=None, unique=True)
    
    mimetype: str | None = Field(default=None)