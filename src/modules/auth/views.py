from fastapi import APIRouter
from src.modules.auth.models import User
from src.shared.dtos import  ListResponse
from fastapi import Query


from typing import Annotated



auth_router = APIRouter(prefix="/auth", tags=["auth"])

from .dtos import UserFilterDTO, UserInputDTO
from .services import AuthService


@auth_router.post("/register")
def register_user(user_data: UserInputDTO) -> User:
    auth_service = AuthService()
    user = auth_service.create_user(user_data.model_dump())
    return user


@auth_router.get("/users")
def get_all_users(params: Annotated[UserFilterDTO, Query()]) -> ListResponse[User]:
    auth_service = AuthService()
    users = auth_service.get_all_users(params)
    return users


