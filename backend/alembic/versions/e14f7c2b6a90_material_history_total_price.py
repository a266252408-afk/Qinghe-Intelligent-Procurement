"""add total price to material history

Revision ID: e14f7c2b6a90
Revises: d83b2c1e7a40
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e14f7c2b6a90"
down_revision: Union[str, None] = "d83b2c1e7a40"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """增加长期材料记录的报价总价字段。"""
    op.add_column(
        "material_history_records",
        sa.Column("total_price", sa.Numeric(12, 2), nullable=True),
    )


def downgrade() -> None:
    """删除长期材料记录的报价总价字段。"""
    op.drop_column("material_history_records", "total_price")
