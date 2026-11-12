"""add account type, team invitations and active project unique index"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c42f1a8d9e20"
down_revision: Union[str, None] = "a91d2f7c4b10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """增加账号类型、团队邀请，并替换错误的软删除唯一约束。"""
    connection = op.get_bind()
    connection.execute(sa.text("ALTER TABLE users ADD COLUMN account_type VARCHAR(20) NOT NULL DEFAULT 'purchaser'"))
    connection.execute(sa.text("DROP INDEX IF EXISTS uq_project_team_name_deleted"))
    connection.execute(sa.text(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_project_team_name_active "
        "ON projects (team_id, name) WHERE is_deleted = 0"
    ))
    op.create_table(
        "team_invitations",
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("inviter_id", sa.Integer(), nullable=False),
        sa.Column("invitee_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
        sa.ForeignKeyConstraint(["inviter_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["invitee_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("team_id", "invitee_id", "status"),
    )
    op.create_index("ix_team_invitations_team_id", "team_invitations", ["team_id"])
    op.create_index("ix_team_invitations_invitee_id", "team_invitations", ["invitee_id"])


def downgrade() -> None:
    """回滚团队邀请和账号类型字段。"""
    op.drop_index("ix_team_invitations_invitee_id", table_name="team_invitations")
    op.drop_index("ix_team_invitations_team_id", table_name="team_invitations")
    op.drop_table("team_invitations")
    op.drop_index("uq_project_team_name_active", table_name="projects")
    op.create_index(
        "uq_project_team_name_deleted", "projects",
        ["team_id", "name", "is_deleted"], unique=True,
    )
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("account_type")
