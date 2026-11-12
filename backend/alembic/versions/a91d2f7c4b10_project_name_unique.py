"""add unique project name per team

Revision ID: a91d2f7c4b10
Revises: f84dc49991e8
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a91d2f7c4b10"
down_revision: Union[str, None] = "f84dc49991e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """同一团队内限制未删除项目名称重复。"""
    connection = op.get_bind()
    connection.execute(sa.text(
        """
        UPDATE projects
        SET is_deleted = 1
        WHERE is_deleted = 0
          AND EXISTS (
              SELECT 1 FROM projects newer
              WHERE newer.team_id = projects.team_id
                AND newer.name = projects.name
                AND newer.is_deleted = 0
                AND newer.id > projects.id
          )
        """
    ))
    op.create_index(
        "uq_project_team_name_active",
        "projects",
        ["team_id", "name"],
        unique=True,
        sqlite_where=sa.text("is_deleted = 0"),
    )


def downgrade() -> None:
    """删除项目名称唯一索引。"""
    op.drop_index("uq_project_team_name_active", table_name="projects")
