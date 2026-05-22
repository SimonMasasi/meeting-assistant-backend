from pydantic import BaseModel

class UserInputDTO(BaseModel):
    username: str
    email: str
    password: str
    first_name:str | None = None
    last_name:str | None = None
    middle_name:str | None = None