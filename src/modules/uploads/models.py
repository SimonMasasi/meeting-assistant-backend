from sqlmodel import Field
from pydantic import computed_field
from src.shared.base_model import BaseModel
from src.shared.enums import FileTypeEnum


class UploadedFile(BaseModel, table=True):
    
    __tablename__ = "uploaded_files"

    filename: str
    content_type: str
    size: int
    file_path: str
    file_type: FileTypeEnum = Field(default=FileTypeEnum.OTHER)
    file_hash: str | None = Field(default=None, unique=True, index=True)
    
    mimetype: str | None = Field(default=None)