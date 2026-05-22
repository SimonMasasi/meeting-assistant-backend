from sqlmodel import Field
from src.shared.base_model import BaseModel


class User(BaseModel, table=True):
    __tablename__ = "users"

    username: str = Field(unique=True)
    email: str = Field(unique=True)
    password: str
    first_name: str | None = Field(default=None)
    last_name: str | None = Field(default=None)
    middle_name: str | None = Field(default=None)
    photo_url: str | None = Field(default=None)


