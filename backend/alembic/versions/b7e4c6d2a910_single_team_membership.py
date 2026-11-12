"""enforce one active team membership per user"""
from typing import Sequence, Union

from alembic import op


revision: str = "b7e4c6d2a910"
down_revision: Union[str, None] = "9c1d4e7f2a60"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """限制一个账号同时只能属于一个团队。"""
    op.create_index("uq_team_member_user", "team_members", ["user_id"], unique=True)


def downgrade() -> None:
    """移除账号团队成员关系的唯一约束。"""
    op.drop_index("uq_team_member_user", table_name="team_members")
