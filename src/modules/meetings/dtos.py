from pydantic import Field
from src.shared.base_model import CamelCaseModel
from src.shared.dtos import BaseFilteringInput


class MeetingInputDTO(CamelCaseModel):
    title: str  = Field(..., min_length=3, max_length=100)
    description: str | None = None
    
    
class MeetingFilteringInputDTO(BaseFilteringInput):
    pass