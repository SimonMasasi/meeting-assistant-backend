from .models import EmailConfiguration
from src.shared.database import engine 
from sqlmodel import Session, select 
from src.shared.dtos import  SingleResponse , ResponseObjects
from  .dtos import EmailInputConfigurationDTO


class SettingsService:
    def __init__(self):
        pass


    def create_or_update_email_configuration(self, email_data: EmailInputConfigurationDTO) -> tuple[bool , str , EmailConfiguration | None]:

        with Session(engine) as session:
            existing_config = session.exec(select(EmailConfiguration)).first()
            if existing_config:
                for key, value in email_data.model_dump().items():
                    setattr(existing_config, key, value)
                session.add(existing_config)
                session.commit()
                session.refresh(existing_config)
                return True, "Email configuration updated successfully", existing_config
            else:
                new_config = EmailConfiguration(**email_data.model_dump())
                session.add(new_config)
                session.commit()
                session.refresh(new_config)
                return True, "Email configuration created successfully", new_config
    
    def get_email_configuration(self) -> SingleResponse[EmailConfiguration]:

        select_statement = select(EmailConfiguration)

        with Session(engine) as session:
            config = session.exec(select_statement).first()
            if config:
                return SingleResponse(response=ResponseObjects.get_response(id=1), data=config)
            else:
                return SingleResponse(response=ResponseObjects.get_response(id=2, message="Email configuration not found"), data=None)