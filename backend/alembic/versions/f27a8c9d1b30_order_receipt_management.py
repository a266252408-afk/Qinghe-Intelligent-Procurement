"""add supplier orders, receipts, and delivery fields

Revision ID: f27a8c9d1b30
Revises: e14f7c2b6a90
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f27a8c9d1b30"
down_revision: Union[str, None] = "e14f7c2b6a90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建下单/收货表并扩展采购项和长期记忆字段。"""
    bind = op.get_bind()
    existing_columns = {column["name"] for column in sa.inspect(bind).get_columns("purchase_items")}
    for name, column in (
        ("supplier_name", sa.String(100)),
        ("supplier_quote_item_id", sa.Integer()),
        ("supplier_quote_price", sa.Numeric(10, 2)),
        ("final_price", sa.Numeric(10, 2)),
    ):
        if name not in existing_columns:
            op.add_column("purchase_items", sa.Column(name, column, nullable=True))

    op.create_table(
        "supplier_orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("purchase_order_id", sa.Integer(), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="ordered"),
        sa.Column("ordered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["purchase_order_id"], ["purchase_orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
        sa.UniqueConstraint("purchase_order_id", name="uq_supplier_order_purchase_order"),
    )
    op.create_index("ix_supplier_orders_purchase_order_id", "supplier_orders", ["purchase_order_id"])
    op.create_index("ix_supplier_orders_team_id", "supplier_orders", ["team_id"])
    op.create_table(
        "supplier_order_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("supplier_order_id", sa.Integer(), nullable=False),
        sa.Column("purchase_item_id", sa.Integer(), nullable=True),
        sa.Column("species", sa.String(100), nullable=False),
        sa.Column("spec", sa.String(100), nullable=False, server_default=""),
        sa.Column("quantity", sa.Numeric(10, 2), nullable=False),
        sa.Column("unit", sa.String(20), nullable=False, server_default=""),
        sa.Column("supplier_name", sa.String(100), nullable=True),
        sa.Column("supplier_quote_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("final_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("total_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["supplier_order_id"], ["supplier_orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["purchase_item_id"], ["purchase_items.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_supplier_order_items_supplier_order_id", "supplier_order_items", ["supplier_order_id"])
    op.create_index("ix_supplier_order_items_purchase_item_id", "supplier_order_items", ["purchase_item_id"])

    history_columns = {column["name"] for column in sa.inspect(bind).get_columns("material_history_records")}
    for name, column in (
        ("ordered_at", sa.DateTime(timezone=True)),
        ("arrived_at", sa.DateTime(timezone=True)),
        ("receipt_status", sa.String(20)),
    ):
        if name not in history_columns:
            op.add_column("material_history_records", sa.Column(name, column, nullable=True))
    op.create_table(
        "receipts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("supplier_order_id", sa.Integer(), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["supplier_order_id"], ["supplier_orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
        sa.UniqueConstraint("supplier_order_id"),
    )
    op.create_index("ix_receipts_supplier_order_id", "receipts", ["supplier_order_id"])
    op.create_index("ix_receipts_team_id", "receipts", ["team_id"])
    op.create_table(
        "receipt_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("receipt_id", sa.Integer(), nullable=False),
        sa.Column("supplier_order_item_id", sa.Integer(), nullable=True),
        sa.Column("species", sa.String(100), nullable=False),
        sa.Column("spec", sa.String(100), nullable=False, server_default=""),
        sa.Column("quantity", sa.Numeric(10, 2), nullable=False),
        sa.Column("unit", sa.String(20), nullable=False, server_default=""),
        sa.Column("supplier_name", sa.String(100), nullable=True),
        sa.Column("final_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("arrived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_received", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["receipt_id"], ["receipts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["supplier_order_item_id"], ["supplier_order_items.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_receipt_items_receipt_id", "receipt_items", ["receipt_id"])


def downgrade() -> None:
    """删除下单/收货表及扩展字段。"""
    op.drop_index("ix_receipt_items_receipt_id", table_name="receipt_items")
    op.drop_table("receipt_items")
    op.drop_index("ix_receipts_team_id", table_name="receipts")
    op.drop_index("ix_receipts_supplier_order_id", table_name="receipts")
    op.drop_table("receipts")
    op.drop_column("material_history_records", "receipt_status")
    op.drop_column("material_history_records", "arrived_at")
    op.drop_column("material_history_records", "ordered_at")
    op.drop_index("ix_supplier_order_items_purchase_item_id", table_name="supplier_order_items")
    op.drop_index("ix_supplier_order_items_supplier_order_id", table_name="supplier_order_items")
    op.drop_table("supplier_order_items")
    op.drop_index("ix_supplier_orders_team_id", table_name="supplier_orders")
    op.drop_index("ix_supplier_orders_purchase_order_id", table_name="supplier_orders")
    op.drop_table("supplier_orders")
    for name in ("final_price", "supplier_quote_price", "supplier_quote_item_id", "supplier_name"):
        op.drop_column("purchase_items", name)
