from fastapi import APIRouter, Depends
from src.modules.auth.models import User
from src.shared.dtos import  ListResponse, ResponseObjects ,SingleResponse
from fastapi import Query
from typing import Annotated
from .dtos import (ChangePasswordInputDTO, UpdateUserInputDTO, UserFilterDTO, UserInputDTO, UserLoginInputDTO, UserLoginResponseDTO
, ForgotPasswordInputDTO , ForgotTokenInputDTO , GoogleAuthInputDTO)
from .services import AuthService
from src.shared.dependencies import get_current_user


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
    return auth_service.get_all_users(params)


@auth_router.post("/login")
def login_user(user_data: UserLoginInputDTO) -> SingleResponse[UserLoginResponseDTO]:
    success, message, user_login_response = auth_service.authenticate_user(user_data)
    if not success:
        return SingleResponse(data=None , response=ResponseObjects.get_response(id=2 , message=message))
    return SingleResponse(data=user_login_response , response=ResponseObjects.get_response(id=1 , message=message))

@auth_router.post("/google")
def login_with_google(google_data: GoogleAuthInputDTO) -> SingleResponse[UserLoginResponseDTO]:
    success, message, user_login_response = auth_service.authenticate_google_user(google_data)
    if not success:
        return SingleResponse(data=None , response=ResponseObjects.get_response(id=2 , message=message))
    return SingleResponse(data=user_login_response , response=ResponseObjects.get_response(id=1 , message=message))


@auth_router.post("/refresh-token")
def refresh_access_token(refresh_token: str) -> SingleResponse[UserLoginResponseDTO]:
    success, message, user_login_response = auth_service.refresh_access_token(refresh_token)
    if not success:
        return SingleResponse(data=None , response=ResponseObjects.get_response(id=2 , message=message))
    return SingleResponse(data=user_login_response , response=ResponseObjects.get_response(id=1 , message=message))


@auth_router.get("/me")
def get_current_user_profile(current_user: User = Depends(get_current_user)) -> SingleResponse[User]:
    return SingleResponse(data=current_user, response=ResponseObjects.get_response(id=1))


@auth_router.put("/update-my-profile")
def update_my_profile(update_data: UpdateUserInputDTO, current_user: User = Depends(get_current_user)) -> SingleResponse[User]:
    success, message, updated_user = auth_service.update_my_profile(current_user.id, update_data)
    if not success:
        return SingleResponse(data=None , response=ResponseObjects.get_response(id=2 , message=message))
    return SingleResponse(data=updated_user , response=ResponseObjects.get_response(id=1 , message=message))

@auth_router.post("/change-password")
def change_password(change_password_data: ChangePasswordInputDTO, current_user: User = Depends(get_current_user)) -> SingleResponse[None]:
    success, message = auth_service.change_password(change_password_data, current_user.id)
    if not success:
        return SingleResponse(data=None , response=ResponseObjects.get_response(id=2 , message=message))
    return SingleResponse(data=None , response=ResponseObjects.get_response(id=1 , message=message))

@auth_router.post("/forgot-password")
def forgot_password(forgot_password_data: ForgotPasswordInputDTO) -> SingleResponse[None]:
    success, message = auth_service.forgot_password(forgot_password_data)
    if not success:
        return SingleResponse(data=None , response=ResponseObjects.get_response(id=2 , message=message))
    return SingleResponse(data=None , response=ResponseObjects.get_response(id=1 , message=message))


@auth_router.post("/request-forgot-password-token")
def request_forgot_password_token(forgot_password_data: ForgotTokenInputDTO) -> SingleResponse[None]:
    success, message = auth_service.request_forgot_password_token(forgot_password_data)
    if not success:
        return SingleResponse(data=None , response=ResponseObjects.get_response(id=2 , message=message))
    return SingleResponse(data=None , response=ResponseObjects.get_response(id=1 , message=message))
