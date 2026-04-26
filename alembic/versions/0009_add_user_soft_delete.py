"""add user soft delete

Revision ID: 0009_add_user_soft_delete
Revises: 0008_add_achievement_overflow_scores
Create Date: 2026-04-27 01:20:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0009_add_user_soft_delete"
down_revision = "0008_add_achievement_overflow_scores"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "user_info" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("user_info")}
    if "is_deleted" not in columns:
        op.add_column("user_info", sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()))
        op.create_index("ix_user_info_is_deleted", "user_info", ["is_deleted"])
    if "deleted_at" not in columns:
        op.add_column("user_info", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "user_info" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("user_info")}
    indexes = {index["name"] for index in inspector.get_indexes("user_info")}
    if "ix_user_info_is_deleted" in indexes:
        op.drop_index("ix_user_info_is_deleted", table_name="user_info")
    if "deleted_at" in columns:
        op.drop_column("user_info", "deleted_at")
    if "is_deleted" in columns:
        op.drop_column("user_info", "is_deleted")
