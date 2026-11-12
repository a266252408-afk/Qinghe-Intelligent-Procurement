# SDD — 项目管理服务（project_service）

> **依据**：system-design.md §2.2.8，PRD §FR-1
> **代码位置**：`backend/app/services/project_service.py`

---

## 1. 功能描述

管理项目的完整生命周期（CRUD），每个项目挂载在一个团队下。
支持按团队、状态筛选项目列表。
不调用大模型，纯确定性代码。

---

## 2. 接口签名

```python
from app.schemas.project import (
    ProjectCreate, ProjectUpdate, ProjectOut, ProjectListOut
)

class ProjectService:

    @staticmethod
    async def create_project(
        data: ProjectCreate,      # 项目创建数据
        creator_id: int,          # 创建者用户 ID
        team_id: int,             # 所属团队 ID
        db: AsyncSession,
    ) -> ProjectOut:
        """创建项目，状态默认为 active。"""

    @staticmethod
    async def list_projects(
        team_id: int,             # 团队 ID（强制过滤）
        status: str | None,       # 筛选状态：active / completed / archived / None（全部）
        db: AsyncSession,
    ) -> ProjectListOut:
        """返回团队下的项目列表，按创建时间倒序。"""

    @staticmethod
    async def get_project(
        project_id: int,
        team_id: int,             # 防越权：必须属于该团队
        db: AsyncSession,
    ) -> ProjectOut:
        """查询单个项目详情。"""

    @staticmethod
    async def update_project(
        project_id: int,
        data: ProjectUpdate,      # 可更新字段：name / budget / status / remark
        team_id: int,
        db: AsyncSession,
    ) -> ProjectOut:
        """更新项目信息。"""

    @staticmethod
    async def delete_project(
        project_id: int,
        team_id: int,
        db: AsyncSession,
    ) -> None:
        """删除项目（软删除：设置 is_deleted=True）。"""
```

### Pydantic 模型（`backend/app/schemas/project.py`）

```python
class ProjectCreate(BaseModel):
    name: str                    # 项目名称
    budget: float | None         # 预算金额
    remark: str | None           # 备注

class ProjectUpdate(BaseModel):
    name: str | None
    budget: float | None
    status: str | None           # active / completed / archived
    remark: str | None

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

class ProjectListOut(BaseModel):
    total: int
    items: list[ProjectOut]
```

---

## 3. 外部依赖

| 依赖 | 用途 |
|:---- |:---- |
| `SQLAlchemy AsyncSession` | 数据库 CRUD |
| `app.models.project.Project` | ORM 模型 |
| `app.core.exceptions` | ProjectNotFoundError |

---

## 4. 异常处理

| 异常类 | 触发条件 | HTTP 状态码 |
|:------- |:-------- |:----------- |
| `ProjectNotFoundError` | project_id 不存在或 team_id 不匹配 | 404 |
| `PermissionError` | 操作者无权限（非 team 成员） | 403 |
