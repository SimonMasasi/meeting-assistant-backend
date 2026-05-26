from fastapi import APIRouter
from .models import EmailConfiguration
from src.shared.dtos import ResponseObjects ,SingleResponse
from .dtos import EmailInputConfigurationDTO
from .services import SettingsService


settings_router = APIRouter(prefix="/settings", tags=["settings"])
settings_service = SettingsService()


@settings_router.post("/email-configuration")
def create_or_update_email_configuration(email_data: EmailInputConfigurationDTO) -> SingleResponse[EmailConfiguration]:
    success, message, config = settings_service.create_or_update_email_configuration(email_data)
    if not success:
        return SingleResponse(data=None , response=ResponseObjects.get_response(id=2 , message=message))
    return SingleResponse(data=config , response=ResponseObjects.get_response(id=1 , message=message))


@settings_router.get("/email-configuration")
def get_email_configuration() -> SingleResponse[EmailConfiguration]:
    return settings_service.get_email_configuration()