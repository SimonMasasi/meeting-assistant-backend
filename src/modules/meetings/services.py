from src.modules.uploads.services import UploadService
from src.modules.uploads.models import UploadedFile 

from .models import Meeting , MeetingSpeaker , MeetingRecording
from .dtos import MeetingInputDTO , MeetingFilteringInputDTO , MeetingRecordingInputDto , MeetingRecordingFilteringInputDTO
from src.shared.database import engine 
from sqlmodel import Session, select 
from src.shared.dtos import  ListResponse , SingleResponse , ResponseObjects
from src.shared.paginated_data import build_paginated_data
from src.utils.audio.speaker_diarization import SpeakerDiarizationService


import logging
logger = logging.getLogger(__name__)



class MeetingService:
    
    def __init__(self):
        self.speaker_diarization_service = SpeakerDiarizationService()
        self.upload_service = UploadService()
    
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
    

    def add_meeting_recording(self,input: MeetingRecordingInputDto , current_user_id: int) -> SingleResponse[list[MeetingRecording]]:
        logger.info("Adding recording to meeting with ID: %s", input.meeting_id)
        # Implementation for adding a recording to a meeting

        #get the file by the given file_id
        with Session(engine) as session:
            recording_file = session.exec(select(UploadedFile).where(UploadedFile.id == input.file_id)).first()
            if not recording_file:
                logger.error("File with ID %s not found", input.file_id)
                return SingleResponse(response=ResponseObjects.get_response(0, "File not found"), data=None)
            
            # TODO process the recording to determine the current speaker (putting a placeholder for now)
            success , message , file_bytes , _ = self.upload_service.get_file(input.file_id)
            if not success:
                logger.error("Failed to retrieve file with ID %s: %s", input.file_id, message)
                return SingleResponse(response=ResponseObjects.get_response(0, message), data=None)
            
            speakers_list = self.speaker_diarization_service.diarize(file_bytes, int(input.meeting_id), current_user_id)

            # Create a new MeetingRecording entry for each speaker segment
            new_recordings = []
            for speaker, start_time, end_time in speakers_list:
                new_recording = MeetingRecording(
                    file_id=recording_file.id,
                    meeting_id=int(input.meeting_id),
                    speaker_id=speaker.id,
                    start_time=str(start_time),
                    end_time=str(end_time)
                )
                session.add(new_recording)
                session.commit()
                session.refresh(new_recording)
                new_recordings.append(new_recording)

        return SingleResponse(response=ResponseObjects.get_response(1), data=new_recordings)
    

    def get_meeting_recordings(self, filtering_input: MeetingRecordingFilteringInputDTO) -> ListResponse[MeetingRecording]:
        logger.info("Retrieving recordings for meeting ID: %s with filters: %s", filtering_input.meeting_id, filtering_input)
        query = select(MeetingRecording).where(MeetingRecording.meeting_id == int(filtering_input.meeting_id))
        return build_paginated_data(filtering=filtering_input,select_function=query)
