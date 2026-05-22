from src.utils.passwords import PasswordManager

from .models import User
from src.shared.database import engine 
from sqlmodel import Session, select 
from src.shared.dtos import  ListResponse
from src.shared.paginated_data import build_paginated_data
from  .dtos import UserFilterDTO


class AuthService:
    def __init__(self):
        pass


    def create_user(self, user_data: dict) -> User:

        password_manager = PasswordManager()
        user_data['password'] = password_manager.hash_password(user_data['password'])

        user = User(**user_data)
        with Session(engine) as session:
            session.add(user)
            session.commit()
            session.refresh(user)
        return user
    
    def get_all_users(self , filtering:UserFilterDTO) -> ListResponse[User]:

        select_statement = select(User)

        if filtering.email:
            select_statement = select_statement.where(User.email == filtering.email)

        return build_paginated_data(
            current_page_number=filtering.page_number,
            size_requested=filtering.items_per_page,
            select_function=select_statement,
            model=User
        )
        
    
    def get_user_by_id(self, user_id: int) -> User | None:
        with Session(engine) as session:
            user = session.get(User, user_id)

        return user