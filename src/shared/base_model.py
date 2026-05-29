from sqlmodel import Field, SQLModel
from sqlalchemy import BigInteger
from pydantic import BaseModel as PydanticBaseModel, ConfigDict, field_serializer
from pydantic.alias_generators import to_camel
from src.utils.generators import  Generator
from datetime import datetime

_camel_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class CamelCaseModel(PydanticBaseModel):
    model_config = _camel_config


class BaseModel(SQLModel):
    model_config = _camel_config

    id: int = Field(primary_key=True, sa_type=BigInteger(), default_factory=Generator.generate_64bit_int_uuid, unique=True)
    is_active: bool = Field(default_factory=lambda: True)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    deleted_at: datetime | None = Field(default=None)

    @field_serializer("id")
    def serialize_id(self, value: int) -> str:
        return str(value)

    class Meta:
        abstract = True
