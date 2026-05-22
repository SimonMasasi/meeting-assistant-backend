from datetime import datetime
import enum
import json
from typing import Generic, List, Optional, Tuple, TypeVar, Union
from pydantic import BaseModel

T = TypeVar("T")

class ResponseObjects(BaseModel):
    id: str
    status: Optional[bool] = None
    code: Optional[int] = None
    message: Optional[str] = None


    @classmethod
    def __read_code_file(cls, code_id):
        file = open('assets/responses.json', 'r')
        file_codes = file.read()
        response_codes = json.loads(file_codes)
        response_code = next(code for code in response_codes if code["id"] == code_id)
        return response_code

    @classmethod
    def get_response(cls,id: Union[int, str],message: Optional[str] = None,) -> "ResponseObjects":
        if isinstance(id, str):
            i_d = int(id)
        else:
            i_d = id
        
        response_code = cls.__read_code_file(i_d)

        return cls(
            id=str(response_code["id"]),
            status=response_code["status"],
            code=response_code["code"],
            message=message if message else response_code["message"],
        )



class PageObject(BaseModel):
    number: int
    has_next_page: bool
    has_previous_page: bool
    current_page_number: int
    next_page_number: int
    previous_page_number: int
    number_of_pages: int
    total_elements: int
    pages_number_array: List[int]

    @classmethod
    def get_page(
        cls,
        total_items: int,
        current_page_number: int,
        size_requested: int,
    ):
        
        previous_page_number = current_page_number - 1 if current_page_number > 1 else 1
        number_of_pages = (total_items // size_requested) + (1 if total_items % size_requested > 0 else 0)

        next_page_number = current_page_number + 1 if current_page_number < number_of_pages else current_page_number


        return cls(
                number=current_page_number,
                has_next_page=current_page_number < number_of_pages,
                has_previous_page=current_page_number > 1,
                current_page_number=current_page_number,
                next_page_number=next_page_number,
                previous_page_number=previous_page_number,
                number_of_pages=number_of_pages,
                total_elements=total_items,
                pages_number_array=list(range(1, number_of_pages + 1))
            )
    
    




class TimeRange(str , enum.Enum):
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    YEARLY = "YEARLY"


class SingleResponse(BaseModel,Generic[T]):
    response: ResponseObjects
    data: Optional[T] = None


class ListResponse(BaseModel ,Generic[T]):
    response: ResponseObjects
    page: Optional[PageObject] = None
    data: Optional[List[T]] = None


class BaseObject(BaseModel):
    id: Optional[str]
    uuid: Optional[str]
    is_active: Optional[bool]
    created_at: Optional[datetime]



class BaseFilteringInput(BaseModel):
    is_active: Optional[bool] = None
    uuid: Optional[str] = None
    search_term: Optional[str] = None
    items_per_page: Optional[int] = None
    page_number: int
    time_range: Optional[TimeRange] = None
    time_from: Optional[datetime] = None
    time_to: Optional[datetime] = None
    ascending: Optional[bool] = None

