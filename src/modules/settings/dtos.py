from pydantic import BaseModel, Field


class EmailInputConfigurationDTO(BaseModel):
    smtp_server: str = Field(..., min_length=1)
    smtp_port: int = Field(..., gt=0)
    username: str  = Field(..., min_length=1)
    password: str = Field(..., min_length=1)
    sender_email: str = Field(..., pattern=r'^\S+@\S+\.\S+$')


