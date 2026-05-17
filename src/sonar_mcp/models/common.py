from pydantic import BaseModel


class Paging(BaseModel):
    pageIndex: int
    pageSize: int
    total: int
