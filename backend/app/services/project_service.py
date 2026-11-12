"""项目管理服务
依据：docs/module-sdd/project_service.md
"""
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DuplicateProjectNameError, ProjectNotFoundError
from app.models.project import Project
from app.schemas.project import ProjectCreate, ProjectListOut, ProjectOut, ProjectUpdate


def _to_out(p: Project) -> ProjectOut:
    return ProjectOut(
        project_id=p.id,
        team_id=p.team_id,
        name=p.name,
        owner_id=p.owner_id,
        budget=float(p.budget) if p.budget is not None else None,
        status=p.status,
        remark=p.remark,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


class ProjectService:

    @staticmethod
    async def create_project(
        data: ProjectCreate, creator_id: int, team_id: int, db: AsyncSession
    ) -> ProjectOut:
        """创建项目，状态默认 active"""
        duplicate = (await db.execute(
            select(Project).where(
                Project.team_id == team_id,
                Project.name == data.name.strip(),
                Project.is_deleted.is_(False),
            )
        )).scalar_one_or_none()
        if duplicate is not None:
            raise DuplicateProjectNameError()
        project = Project(
            team_id=team_id,
            name=data.name.strip(),
            owner_id=creator_id,
            budget=data.budget,
            remark=data.remark,
            status="active",
        )
        db.add(project)
        await db.flush()
        return _to_out(project)

    @staticmethod
    async def list_projects(
        team_id: int, status: str | None, db: AsyncSession
    ) -> ProjectListOut:
        """返回团队项目列表，按创建时间倒序"""
        stmt = (
            select(Project)
            .where(Project.team_id == team_id, Project.is_deleted.is_(False))
            .order_by(Project.created_at.desc())
        )
        if status:
            stmt = stmt.where(Project.status == status)

        rows = (await db.execute(stmt)).scalars().all()
        return ProjectListOut(total=len(rows), items=[_to_out(p) for p in rows])

    @staticmethod
    async def get_project(project_id: int, team_id: int, db: AsyncSession) -> ProjectOut:
        """查询单个项目，校验 team_id 防越权"""
        project = await db.get(Project, project_id)
        if project is None or project.team_id != team_id or project.is_deleted:
            raise ProjectNotFoundError()
        return _to_out(project)

    @staticmethod
    async def update_project(
        project_id: int, data: ProjectUpdate, team_id: int, db: AsyncSession
    ) -> ProjectOut:
        """更新项目信息"""
        project = await db.get(Project, project_id)
        if project is None or project.team_id != team_id or project.is_deleted:
            raise ProjectNotFoundError()

        if data.name is not None:
            project.name = data.name
        if data.budget is not None:
            project.budget = data.budget
        if data.status is not None:
            project.status = data.status
        if data.remark is not None:
            project.remark = data.remark
        project.updated_at = datetime.now(timezone.utc)
        await db.flush()
        return _to_out(project)

    @staticmethod
    async def delete_project(project_id: int, team_id: int, db: AsyncSession) -> None:
        """软删除项目"""
        project = await db.get(Project, project_id)
        if project is None or project.team_id != team_id or project.is_deleted:
            raise ProjectNotFoundError()
        project.is_deleted = True
        project.updated_at = datetime.now(timezone.utc)
        await db.flush()
