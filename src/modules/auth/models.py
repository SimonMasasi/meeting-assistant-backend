from sqlmodel import Field , select , Session
from sqlalchemy import BigInteger
from pydantic import computed_field
from src.shared.base_model import BaseModel
from src.shared.enums import UserTypeEnum , UserAuthTokensTypes , AuthProviderEnum
from src.modules.uploads.models import UploadedFile
from src.shared.database import engine
from datetime import datetime




class User(BaseModel, table=True):
    __tablename__ = "users"

    username: str = Field(unique=True)
    email: str = Field(unique=True)
    password: str | None = Field(default=None, exclude=True)
    auth_provider: AuthProviderEnum = Field(default=AuthProviderEnum.LOCAL)
    email_verified: bool = Field(default=False)
    google_sub: str | None = Field(default=None, unique=True, exclude=True)
    first_name: str | None = Field(default=None)
    last_name: str | None = Field(default=None)
    middle_name: str | None = Field(default=None)
    photo_id: int | None = Field(foreign_key="uploaded_files.id", default=None, exclude=True , sa_type=BigInteger())
    user_type: UserTypeEnum | None = Field(default=UserTypeEnum.NORMAL_USER)
    account_locked: bool | None = Field(default=False)
    failed_login_attempts: int | None = Field(default=0)

    @computed_field
    @property
    def full_name(self) -> str:
        names = [self.first_name, self.middle_name, self.last_name]
        return " ".join(name for name in names if name)
    

    @computed_field
    @property
    def photo(self) -> UploadedFile | None:
        if self.photo_id is None:
            return None
        with Session(engine) as session:
            return session.exec(select(UploadedFile).where(UploadedFile.id == self.photo_id)).first()
        

class UserAuthToken(BaseModel, table=True):
    __tablename__ = "user_auth_tokens"

    user_id: int = Field(foreign_key="users.id", sa_type=BigInteger(), exclude=True)
    token: str = Field(unique=True , exclude=True)
    expires_at: datetime
    token_type: UserAuthTokensTypes

    def is_expired(self) -> bool:
        return datetime.now() > self.expires_at