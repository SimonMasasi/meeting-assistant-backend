from .dtos import PageObject , ListResponse , ResponseObjects ,BaseFilteringInput
from typing import TypeVar

from src.shared.database import engine 
from sqlmodel import Session, String, func, select, or_
from sqlmodel.sql._expression_select_cls import SelectOfScalar

T= TypeVar("T")

def build_paginated_data(current_page_number: int, size_requested: int ,select_function: SelectOfScalar[T],
                        filtering: BaseFilteringInput) -> ListResponse[T]:

    try:

        offset = (current_page_number - 1) * size_requested


        with Session(engine) as session:

            total_items = session.exec(select(func.count()).select_from(select_function.subquery())).one()

            #check if the offset is out of range
            if offset >= total_items:
                return ListResponse(response=ResponseObjects.get_response(id=3 , message="Page number out of range"))
            
            if filtering.id:
                select_function = select_function.where(func.cast(select_function.selected_columns["id"], String) == filtering.id)

            if filtering.search_term:
                select_function = apply_search_filter(select_function, filtering.search_term)

            items = session.exec(select_function.offset(offset).limit(size_requested)).all()

        page_object = PageObject.get_page(total_items=total_items,current_page_number=current_page_number,size_requested=size_requested)

        return ListResponse(response=ResponseObjects.get_response(id=1),page=page_object,data=items)
    except Exception as e:
        e.with_traceback()
        return ListResponse(response=ResponseObjects.get_response(id=2 , message=str(e)),page=None,data=None)




def apply_search_filter(select_function: SelectOfScalar[T] , search_term: str) -> SelectOfScalar[T]:
    # apply search filter to all string values in a model from the select function
    search_term = f"%{search_term}%"

    STRING_TYPES = {'AutoString', 'String', 'VARCHAR', 'Text', 'TEXT', 'CHAR', 'NVARCHAR', 'NCHAR'}
    conditions = [
        column.ilike(search_term)
        for column in select_function.selected_columns
        if type(column.type).__name__ in STRING_TYPES
    ]
    if conditions:
        select_function = select_function.where(or_(*conditions))
    return select_function
    