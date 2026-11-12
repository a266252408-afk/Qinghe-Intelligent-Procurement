"""add project to material history

Revision ID: b9f3a5c7d210
Revises: b7e4c6d2a910
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b9f3a5c7d210"
down_revision: Union[str, None] = "b7e4c6d2a910"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """长期材料记录增加项目归属：新增 project_id 并按来源报价回填。"""
    with op.batch_alter_table("material_history_records") as batch:
        batch.add_column(sa.Column("project_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_material_history_project_id", "projects", ["project_id"], ["id"]
        )
    op.create_index(
        "ix_material_history_team_project",
        "material_history_records",
        ["team_id", "project_id"],
    )
    # 存量数据回填：报价记录 → 采购单 → 项目
    op.execute(
        """
        UPDATE material_history_records
        SET project_id = (
            SELECT purchase_orders.project_id
            FROM quotes
            JOIN purchase_orders ON quotes.order_id = purchase_orders.id
            WHERE material_history_records.source_quote_id = quotes.id
        )
        WHERE material_history_records.source_quote_id IS NOT NULL
          AND material_history_records.project_id IS NULL
        """
    )


def downgrade() -> None:
    """删除长期材料记录的项目归属字段。"""
    op.drop_index("ix_material_history_team_project", table_name="material_history_records")
    with op.batch_alter_table("material_history_records") as batch:
        batch.drop_constraint("fk_material_history_project_id", type_="foreignkey")
        batch.drop_column("project_id")
