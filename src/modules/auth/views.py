from fastapi import APIRouter
from src.modules.auth.models import User
from src.shared.dtos import  ListResponse, ResponseObjects ,SingleResponse
from fastapi import Query
from typing import Annotated
from .dtos import UserFilterDTO, UserInputDTO, UserLoginInputDTO, UserLoginResponseDTO
from .services import AuthService


auth_router = APIRouter(prefix="/auth", tags=["auth"])
auth_service = AuthService()


@auth_router.post("/register")
def register_user(user_data: UserInputDTO) -> SingleResponse[User]:
    success, message, user = auth_service.create_user(user_data)
    if not success:
        return SingleResponse(data=None , response=ResponseObjects.get_response(id=2 , message=message))
    return SingleResponse(data=user , response=ResponseObjects.get_response(id=1 , message=message))


@auth_router.get("/users")
def get_all_users(params: Annotated[UserFilterDTO, Query()]) -> ListResponse[User]:
    users = auth_service.get_all_users(params)
    return users


@auth_router.post("/login")
def login_user(user_data: UserLoginInputDTO) -> SingleResponse[UserLoginResponseDTO]:
    success, message, user_login_response = auth_service.authenticate_user(user_data)
    if not success:
        return SingleResponse(data=None , response=ResponseObjects.get_response(id=2 , message=message))
    return SingleResponse(data=user_login_response , response=ResponseObjects.get_response(id=1 , message=message))

@auth_router.post("/refresh-token")
def refresh_access_token(refresh_token: str) -> SingleResponse[UserLoginResponseDTO]:
    success, message, user_login_response = auth_service.refresh_access_token(refresh_token)
    if not success:
        return SingleResponse(data=None , response=ResponseObjects.get_response(id=2 , message=message))
    return SingleResponse(data=user_login_response , response=ResponseObjects.get_response(id=1 , message=message))


