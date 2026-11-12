"""add quote uploads and material history records

Revision ID: d83b2c1e7a40
Revises: c42f1a8d9e20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d83b2c1e7a40"
down_revision: Union[str, None] = "c42f1a8d9e20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建报价上传和长期材料历史记录表。"""
    op.add_column("quotes", sa.Column("quote_date", sa.Date(), nullable=True))
    op.add_column("quote_items", sa.Column("unit", sa.String(length=20), nullable=False, server_default=""))
    op.add_column("quote_items", sa.Column("final_price", sa.Numeric(10, 2), nullable=True))
    op.create_table(
        "quote_uploads",
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("uploaded_by", sa.Integer(), nullable=False),
        sa.Column("file_path", sa.String(length=500), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("confirmed_by", sa.Integer(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["confirmed_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_quote_uploads_team_id", "quote_uploads", ["team_id"])
    op.create_table(
        "material_history_records",
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("supplier_name", sa.String(length=100), nullable=False),
        sa.Column("material_name", sa.String(length=100), nullable=False),
        sa.Column("spec", sa.String(length=100), nullable=False),
        sa.Column("quantity", sa.Numeric(10, 2), nullable=True),
        sa.Column("unit", sa.String(length=20), nullable=False),
        sa.Column("quote_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("final_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("quote_date", sa.Date(), nullable=True),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("delivery_days", sa.Integer(), nullable=True),
        sa.Column("payment_terms", sa.Text(), nullable=True),
        sa.Column("source_file", sa.String(length=500), nullable=False),
        sa.Column("source_quote_id", sa.Integer(), nullable=True),
        sa.Column("uploaded_by", sa.Integer(), nullable=True),
        sa.Column("confirmed_by", sa.Integer(), nullable=True),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
        sa.ForeignKeyConstraint(["source_quote_id"], ["quotes.id"]),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["confirmed_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("team_id", "fingerprint", name="uq_material_history_team_fingerprint"),
    )
    op.create_index("ix_material_history_records_team_id", "material_history_records", ["team_id"])
    op.create_index("ix_material_history_team_supplier", "material_history_records", ["team_id", "supplier_name"])
    op.create_index("ix_material_history_team_material", "material_history_records", ["team_id", "material_name"])
    op.create_index("ix_material_history_team_date", "material_history_records", ["team_id", "quote_date"])


def downgrade() -> None:
    """删除报价上传和长期材料历史记录表。"""
    op.drop_index("ix_material_history_team_date", table_name="material_history_records")
    op.drop_index("ix_material_history_team_material", table_name="material_history_records")
    op.drop_index("ix_material_history_team_supplier", table_name="material_history_records")
    op.drop_index("ix_material_history_records_team_id", table_name="material_history_records")
    op.drop_table("material_history_records")
    op.drop_index("ix_quote_uploads_team_id", table_name="quote_uploads")
    op.drop_table("quote_uploads")
    op.drop_column("quote_items", "final_price")
    op.drop_column("quote_items", "unit")
    op.drop_column("quotes", "quote_date")
