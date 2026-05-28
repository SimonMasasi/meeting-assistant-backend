from .models import Meeting
from .dtos import MeetingInputDTO , MeetingFilteringInputDTO
from src.shared.database import engine 
from sqlmodel import Session, select 
from src.shared.dtos import  ListResponse , SingleResponse , ResponseObjects
from src.shared.paginated_data import build_paginated_data


import logging
logger = logging.getLogger(__name__)



class MeetingService:
    
    def __init__(self):
        pass
    
    def create_meeting(self, meeting_input: MeetingInputDTO , current_user_id: int) -> SingleResponse[Meeting]:
        logger.info("Creating meeting with title: %s", meeting_input.title)
        with Session(engine) as session:
            new_meeting = Meeting(
                title=meeting_input.title,
                description=meeting_input.description,
                created_by_id=current_user_id
            )
            session.add(new_meeting)
            session.commit()
            session.refresh(new_meeting)
        return SingleResponse(response=ResponseObjects.get_response(1), data=new_meeting)
        
    def get_meetings(self, filtering_input: MeetingFilteringInputDTO , current_user_id: int) -> ListResponse[Meeting]:
        logger.info("Retrieving meetings with filters: %s", filtering_input)
        query = select(Meeting).where(Meeting.created_by_id == current_user_id)
        return build_paginated_data(filtering=filtering_input,select_function=query)