from pydantic import Field
from src.shared.base_model import CamelCaseModel
from src.shared.dtos import BaseFilteringInput
from typing import Optional
from .models import User

class UserInputDTO(CamelCaseModel):
    username: str  = Field(..., min_length=3, max_length=50)
    email: str = Field(..., pattern=r'^\S+@\S+\.\S+$')
    password: str = Field(..., min_length=8)
    first_name:str | None = None
    last_name:str | None = None
    middle_name:str | None = None


class UpdateUserInputDTO(CamelCaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    middle_name: Optional[str] = None
    photo_id: Optional[str] = None


class ChangePasswordInputDTO(CamelCaseModel):
    current_password: str | None = Field(..., min_length=8 , nullable=True)
    new_password: str = Field(..., min_length=8)
    verify_new_password: str = Field(..., min_length=8)

class ForgotTokenInputDTO(CamelCaseModel):
    email: str = Field(..., pattern=r'^\S+@\S+\.\S+$')

class ForgotPasswordInputDTO(CamelCaseModel):
    token: str
    new_password: str = Field(..., min_length=8)
    verify_new_password: str = Field(..., min_length=8)


 
class UserFilterDTO(BaseFilteringInput):
    email: Optional[str] = None
    
class UserLoginInputDTO(CamelCaseModel):
    username: str
    password: str
    
    
class UserLoginResponseDTO(CamelCaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 3600
    user: User