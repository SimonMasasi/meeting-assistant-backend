from sqlmodel import Field, SQLModel
from pydantic import field_serializer
from src.utils.generators import  Generator
from datetime import datetime

class BaseModel(SQLModel):

    id: int = Field(primary_key=True , default_factory=Generator.generate_64bit_int_uuid , unique=True)
    is_active: bool = Field(default_factory=lambda: True)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    deleted_at: datetime | None = Field(default=None)

    @field_serializer("id")
    def serialize_id(self, value: int) -> str:
        return str(value)

    class Meta:
        abstract = True
