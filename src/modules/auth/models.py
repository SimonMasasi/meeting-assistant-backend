from sqlmodel import Field
from src.shared.base_model import BaseModel
from src.shared.enums import UserTypeEnum



class User(BaseModel, table=True):
    __tablename__ = "users"

    username: str = Field(unique=True)
    email: str = Field(unique=True)
    password: str = Field(exclude=True)
    first_name: str | None = Field(default=None)
    last_name: str | None = Field(default=None)
    middle_name: str | None = Field(default=None)
    photo_url: str | None = Field(default=None)
    user_type: UserTypeEnum | None = Field(default=UserTypeEnum.NORMAL_USER)


    @property
    def full_name(self) -> str:
        names = [self.first_name, self.middle_name, self.last_name]
        return " ".join(name for name in names if name)
    
