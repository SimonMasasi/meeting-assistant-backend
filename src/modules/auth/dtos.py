from pydantic import BaseModel
from src.shared.dtos import BaseFilteringInput
from typing import Optional

class UserInputDTO(BaseModel):
    username: str
    email: str
    password: str
    first_name:str | None = None
    last_name:str | None = None
    middle_name:str | None = None

class UserFilterDTO(BaseFilteringInput):
    email: Optional[str] = None