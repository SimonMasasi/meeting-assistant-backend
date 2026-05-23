from fastapi import APIRouter
from src.modules.auth.models import User
from src.shared.dtos import  ListResponse, ResponseObjects ,SingleResponse
from fastapi import Query
from typing import Annotated
from .dtos import UserFilterDTO, UserInputDTO
from .services import AuthService


auth_router = APIRouter(prefix="/auth", tags=["auth"])


@auth_router.post("/register")
def register_user(user_data: UserInputDTO) -> SingleResponse[User]:
    auth_service = AuthService()
    success, message, user = auth_service.create_user(user_data)
    if not success:
        return SingleResponse(data=None , response=ResponseObjects.get_response(id=2 , message=message))
    return SingleResponse(data=user , response=ResponseObjects.get_response(id=1 , message=message))


@auth_router.get("/users")
def get_all_users(params: Annotated[UserFilterDTO, Query()]) -> ListResponse[User]:
    auth_service = AuthService()
    users = auth_service.get_all_users(params)
    return users


