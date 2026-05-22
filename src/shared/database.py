from sqlmodel import SQLModel, create_engine
from config import SETTINGS

engine = create_engine(SETTINGS.DATABASE_URL)


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)