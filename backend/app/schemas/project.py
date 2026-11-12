"""项目相关 Pydantic Schema"""
from datetime import datetime
from pydantic import BaseModel


class ProjectCreate(BaseModel):
    name: str
    budget: float | None = None
    remark: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    budget: float | None = None
    status: str | None = None    # active / completed / archived
    remark: str | None = None


class ProjectOut(BaseModel):
    project_id: int
    team_id: int
    name: str
    owner_id: int
    budget: float | None
    status: str
    remark: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectListOut(BaseModel):
    total: int
    items: list[ProjectOut]
