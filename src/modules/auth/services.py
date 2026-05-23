from src.utils.passwords import PasswordManager

from .models import User
from src.shared.database import engine 
from sqlmodel import Session, select 
from src.shared.dtos import  ListResponse
from src.shared.paginated_data import build_paginated_data
from  .dtos import UserFilterDTO , UserInputDTO


class AuthService:
    def __init__(self):
        pass


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