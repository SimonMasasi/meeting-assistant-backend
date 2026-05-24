from sqlmodel import Field
from src.shared.base_model import BaseModel


class EmailConfiguration(BaseModel, table=True):
    __tablename__ = "email_configurations"

    smtp_server: str
    smtp_port: int
    username: str
    password: str = Field(exclude=True)
    sender_email: str