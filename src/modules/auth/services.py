from src.utils.passwords import PasswordManager

from .models import User
from src.shared.database import engine 
from sqlmodel import Session, select 


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
    
    def get_all_users(self) -> list[User]:
        with Session(engine) as session:
            users = session.exec(select(User)).all()
        return users
    
    def get_user_by_id(self, user_id: int) -> User | None:
        with Session(engine) as session:
            user = session.get(User, user_id)

        return user