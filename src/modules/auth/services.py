from datetime import timedelta
from datetime import datetime

from config import SETTINGS
from src.utils.passwords import PasswordManager

from .models import User, UserAuthToken , UserAuthTokensTypes
from src.shared.database import engine 
from sqlmodel import Session, select  , delete
from src.shared.dtos import  ListResponse
from src.shared.paginated_data import build_paginated_data
from  .dtos import UserFilterDTO , UserInputDTO , UserLoginResponseDTO , UserLoginInputDTO , UpdateUserInputDTO , ChangePasswordInputDTO , ForgotPasswordInputDTO , ForgotTokenInputDTO
from src.utils.jwt_auth import JWTAuth
from src.shared.enums import FileTypeEnum , UserAuthTokensTypes

import logging
logger = logging.getLogger(__name__)


class AuthService:
    def __init__(self):
        self.jwt_auth = JWTAuth()
        self.LOGIN_ATTEMPT_LIMIT = 5
        self.password_manager = PasswordManager()
        
        
    def authenticate_user(self, input: UserLoginInputDTO) -> tuple[bool , str , UserLoginResponseDTO | None]:
        logger.info("Authenticating user: %s", input.username)
        with Session(engine) as session:
            user = session.exec(select(User).where(User.username == input.username)).first()
            if not user:
                logger.warning("Authentication failed for username: %s", input.username)
                return False, "Invalid username or password", None
            
            if not self.password_manager.verify_password(input.password, user.password):
                #increment failed login attempts
                user.failed_login_attempts += 1
                #lock account if failed login attempts exceed limit
                if user.failed_login_attempts >= self.LOGIN_ATTEMPT_LIMIT:
                    user.account_locked = True
                    logger.warning("Account locked for username: %s due to too many failed login attempts", input.username)
                session.add(user)
                session.commit()
                return False, "Invalid username or password", None
            
            if user.account_locked:
                return False, "Account is locked due to too many failed login attempts", None
            
            #reset failed login attempts on successful login
            user.failed_login_attempts = 0
            session.add(user)
            session.commit()
            
            #generate JWT tokens
            access_token, refresh_token , expires_in = self.jwt_auth.create_access_token_and_refresh_token(user)
            user_login_response = UserLoginResponseDTO(
                access_token=access_token,
                refresh_token=refresh_token,
                expires_in=expires_in,
                user=user
            )

            return True, "Authentication successful", user_login_response
        
        
    def refresh_access_token(self, refresh_token: str) -> tuple[bool , str , UserLoginResponseDTO | None]:
        try:
            payload = self.jwt_auth.decode(refresh_token)
            user_id = payload.get("user_id")
            if not user_id:
                return False, "Invalid refresh token", None
            
            with Session(engine) as session:
                user = session.exec(select(User).where(User.id == user_id)).first()
                if not user:
                    return False, "User not found", None
                
                access_token, new_refresh_token , expires_in = self.jwt_auth.create_access_token_and_refresh_token(user)
                user_login_response = UserLoginResponseDTO(
                    access_token=access_token,
                    refresh_token=new_refresh_token,
                    expires_in=expires_in,
                    user=user
                )
                return True, "Access token refreshed successfully", user_login_response
        except Exception as e:
            logger.error("Error refreshing access token: %s", str(e))
            return False, "Invalid refresh token", None


    def create_user(self, user_data: UserInputDTO) -> tuple[bool , str , User | None]:
        #check if password is strong
        is_strong , message = self.password_manager.is_strong_password(user_data.password)
        if not is_strong:
            return False, message, None
               

        with Session(engine) as session:
            existing_user = session.exec(select(User).where(User.email == user_data.email)).first()
            if existing_user:
                return False, "Email already exists", None
            existing_user = session.exec(select(User).where(User.username == user_data.username)).first()
            if existing_user:
                return False, "Username already exists", None
            
            user_data.password = self.password_manager.hash_password(user_data.password)
            user = User(**user_data.model_dump())
            
            session.add(user)
            session.commit()
            session.refresh(user)
             
        return True, "User created successfully", user
    
    def get_all_users(self , filtering:UserFilterDTO) -> ListResponse[User]:

        select_statement = select(User)

        if filtering.email:
            select_statement = select_statement.where(User.email == filtering.email)

        return build_paginated_data(
            select_function=select_statement,
            filtering=filtering
        )
        
    def get_profile_from_token(self, token: str) -> tuple[bool , str , User | None]:
        try:
            payload = self.jwt_auth.decode(token)
            user_id = payload.get("user_id")
            if not user_id:
                return False, "Invalid token", None
            
            with Session(engine) as session:
                user = session.exec(select(User).where(User.id == user_id)).first()
                if not user:
                    return False, "User not found", None
                
                return True, "User profile retrieved successfully", user
        except Exception as e:
            logger.error("Error retrieving user profile from token: %s", str(e))
            return False, "Invalid token", None
        

    def update_my_profile(self, user_id: int, update_data: UpdateUserInputDTO) -> tuple[bool , str , User | None]:
        with Session(engine) as session:
            user = session.exec(select(User).where(User.id == user_id)).first()
            if not user:
                return False, "User not found", None
            
            #check if photo_id is being updated and if so, verify that the file exists
            if update_data.photo_id:
                from src.modules.uploads.models import UploadedFile
                file = session.exec(select(UploadedFile).where(UploadedFile.id == update_data.photo_id)).first()
                if not file:
                    return False, "Photo file not found", None
                
                if file.file_type != FileTypeEnum.IMAGE:
                    return False, "Uploaded file is not an image", None
                
            #change photo_id to int if it's not None
            if update_data.photo_id is not None:
                try:
                    update_data.photo_id = int(update_data.photo_id)
                except ValueError:
                    update_data.photo_id = None
                            
            for field, value in update_data.model_dump(exclude_unset=True).items():
                setattr(user, field, value)
            
            session.add(user)
            session.commit()
            session.refresh(user)
        
        return True, "User profile updated successfully", user
    

    def change_password(self,input: ChangePasswordInputDTO, user_id: int) -> tuple[bool , str]:
        user_auth_token = None
        with Session(engine) as session:
            user = session.exec(select(User).where(User.id == user_id)).first()
            if not user:
                return False, "User not found"
            if not user_auth_token:
                return False, "Invalid or expired token"

            if not self.password_manager.verify_password(input.current_password, user.password):
                return False, "Current password is incorrect"
            
            is_strong , message = self.password_manager.is_strong_password(input.new_password)
            if not is_strong:
                return False, message
            
            user.password = self.password_manager.hash_password(input.new_password)
            session.add(user)

            session.commit()
        
        return True, "Password changed successfully"
    

    def request_forgot_password_token(self, input: ForgotTokenInputDTO) -> tuple[bool , str]:
        with Session(engine) as session:
            user = session.exec(select(User).where(User.email == input.email)).first()
            if not user:
                return False, "if the email exists in our system, a password reset email will be sent"
            
            #generate password reset token
            reset_token = self.jwt_auth.create_password_reset_token(user)
            #store password reset token in database
            user_auth_token = UserAuthToken(
                user_id=user.id,
                token=reset_token,
                expires_at=datetime.now() + timedelta(seconds=SETTINGS.JWT_PASSWORD_RESET_TOKEN_EXPIRE_SECONDS),
                token_type=UserAuthTokensTypes.FORGET_PASSWORD
            )
            session.add(user_auth_token)
            session.commit()

            #send password reset email
            # self.email_service.send_password_reset_email(user.email, reset_token)
        
        return True, "if the email exists in our system, a password reset email will be sent"
    

    def forgot_password(self, input: ForgotPasswordInputDTO) -> tuple[bool , str]:
        with Session(engine) as session:
            user_auth_token = session.exec(select(UserAuthToken).where(UserAuthToken.token == input.token, UserAuthToken.token_type == UserAuthTokensTypes.FORGET_PASSWORD)).first()
            if not user_auth_token:
                return False, "Invalid or expired token"
            
            user = session.exec(select(User).where(User.id == user_auth_token.user_id)).first()
            if not user:
                return False, "User not found"

            is_strong , message = self.password_manager.is_strong_password(input.new_password)
            if not is_strong:
                return False, message
            
            user.password = self.password_manager.hash_password(input.new_password)
            session.add(user)

            #delete all forget password tokens for the user
            session.exec(delete(UserAuthToken).where(UserAuthToken.user_id == user.id, UserAuthToken.token_type == UserAuthTokensTypes.FORGET_PASSWORD))
            session.commit()
        
        return True, "Password reset successfully"