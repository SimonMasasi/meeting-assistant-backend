from .dtos import PageObject , ListResponse , ResponseObjects
from typing import TypeVar

from src.shared.database import engine 
from sqlmodel import Session, func, select
from sqlmodel.sql._expression_select_cls import SelectOfScalar

T= TypeVar("T")

def build_paginated_data(current_page_number: int, size_requested: int ,select_function: SelectOfScalar[T] , model: T):


    try:

        offset = (current_page_number - 1) * size_requested


        with Session(engine) as session:

            total_items = session.exec(select(func.count()).select_from(select_function.subquery())).one()

            #check if the offset is out of range
            if offset >= total_items:
                return ListResponse(
                    response=ResponseObjects.get_response(id=3 , message="Page number out of range"),
                    page=None,
                    data=None
                )

            items = session.exec(select_function.offset(offset).limit(size_requested)).all()

        page_object = PageObject.get_page(
            total_items=total_items,
            current_page_number=current_page_number,
            size_requested=size_requested,
        )

        return ListResponse(
            response=ResponseObjects.get_response(id=1),
            page=page_object,
            data=items
        )
    except Exception as e:
        e.with_traceback()
        print(e)
        return ListResponse(
            response=ResponseObjects.get_response(id=2 , message=str(e)),
            page=None,
            data=None
        )



    