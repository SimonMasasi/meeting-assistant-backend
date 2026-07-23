from sqlmodel import Field
from sqlalchemy import BigInteger
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
    # BigInteger: a 2 GB upload overflows a 32-bit int by design (int4 tops out
    # one byte short of 2 GiB).
    size: int = Field(sa_type=BigInteger())
    file_path: str
    file_type: FileTypeEnum = Field(default=FileTypeEnum.OTHER)
    file_hash: str | None = Field(default=None, unique=True)

    mimetype: str | None = Field(default=None)


class TusUpload(BaseModel, table=True):
    """An in-progress resumable (tus) upload.

    Tracks how much of the file has arrived so a client can resume after a
    dropped connection. The bytes themselves live in a scratch file at
    `temp_path` until the upload completes, at which point they are streamed
    into the storage provider and an `UploadedFile` row is created.
    """

    __tablename__ = "tus_uploads"

    # Opaque id that appears in the tus Location URL.
    upload_key: str = Field(unique=True, index=True)

    filename: str
    content_type: str | None = Field(default=None)
    # Declared total from the Upload-Length header, and how much has landed.
    total_size: int = Field(sa_type=BigInteger())
    offset: int = Field(default=0, sa_type=BigInteger())
    temp_path: str

    # Only the creator may HEAD/PATCH/DELETE this upload.
    owner_id: int = Field(foreign_key="users.id", sa_type=BigInteger(), exclude=True)
    expires_at: datetime
    # Set once finalized; also marks the upload as no longer resumable.
    uploaded_file_id: int | None = Field(
        default=None, foreign_key="uploaded_files.id", sa_type=BigInteger()
    )