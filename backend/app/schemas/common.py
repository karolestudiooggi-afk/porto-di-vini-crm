from typing import Generic, TypeVar

from pydantic import BaseModel


T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    total: int
    limit: int
    offset: int
    items: list[T]


class CountByValue(BaseModel):
    valor: str
    total: int
