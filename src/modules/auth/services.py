from src.utils.passwords import PasswordManager

from .models import User
from src.shared.database import engine 
from sqlmodel import Session, select 
from src.shared.dtos import  ListResponse
from src.shared.paginated_data import build_paginated_data
from  .dtos import UserFilterDTO , UserInputDTO , UserLoginResponseDTO , UserLoginInputDTO
from src.utils.jwt_auth import JWTAuth

import logging
logger = logging.getLogger(__name__)


class AuthService:
    def __init__(self):
        self.jwt_auth = JWTAuth()
        self.LOGIN_ATTEMPT_LIMIT = 5
        
        
    def authenticate_user(self, input: UserLoginInputDTO) -> tuple[bool , str , UserLoginResponseDTO | None]:
        logger.info("Authenticating user: %s", input.username)
        with Session(engine) as session:
            user = session.exec(select(User).where(User.username == input.username)).first()
            if not user:
                logger.warning("Authentication failed for username: %s", input.username)
                return False, "Invalid username or password", None
            
            password_manager = PasswordManager()
            if not password_manager.verify_password(input.password, user.password):
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


    def create_user(self, user_data: UserInputDTO) -> tuple[bool , str , User | None]:

        password_manager = PasswordManager()
        user_data.password = password_manager.hash_password(user_data.password)

        #check if password is strong
        is_strong , message = password_manager.is_strong_password(user_data.password)
        if not is_strong:
            return False, message, None
        
        #check if email or username already exists
        with Session(engine) as session:
            existing_user = session.exec(select(User).where(User.email == user_data.email)).first()
            if existing_user:
                return False, "Email already exists", None
            existing_user = session.exec(select(User).where(User.username == user_data.username)).first()
            if existing_user:
                return False, "Username already exists", None

        user = User(**user_data.model_dump())
        with Session(engine) as session:
            session.add(user)
            session.commit()
            session.refresh(user)
        return True, "User created successfully", user
    
    def get_all_users(self , filtering:UserFilterDTO) -> ListResponse[User]:

        select_statement = select(User)

        if filtering.email:
            select_statement = select_statement.where(User.email == filtering.email)

        return build_paginated_data(
            current_page_number=filtering.page_number,
            size_requested=filtering.items_per_page,
            select_function=select_statement,
            filtering=filtering
        )