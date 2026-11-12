"""add custom purchase order name

Revision ID: 9c1d4e7f2a60
Revises: f27a8c9d1b30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9c1d4e7f2a60"
down_revision: Union[str, None] = "f27a8c9d1b30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """为采购单增加可选自定义名称。"""
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("purchase_orders")}
    if "name" not in columns:
        op.add_column("purchase_orders", sa.Column("name", sa.String(length=120), nullable=True))


def downgrade() -> None:
    """移除采购单自定义名称。"""
    op.drop_column("purchase_orders", "name")
