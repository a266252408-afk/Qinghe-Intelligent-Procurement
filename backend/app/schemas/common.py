"""通用 Pydantic Schema"""
from typing import Any
from pydantic import BaseModel


class Pagination(BaseModel):
    page: int = 1
    page_size: int = 20


class TokenPayload(BaseModel):
    user_id: int
    team_id: int | None = None
    role: str | None = None
    exp: int
