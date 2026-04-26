"""add announcement scope binding

Revision ID: 0010_add_announcement_scope_binding
Revises: 0009_add_user_soft_delete
Create Date: 2026-04-27 02:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0010_add_announcement_scope_binding"
down_revision = "0009_add_user_soft_delete"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "announcement_scope_binding" in inspector.get_table_names():
        return

    op.create_table(
        "announcement_scope_binding",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("announcement_id", sa.Integer(), nullable=False),
        sa.Column("archive_record_id", sa.Integer(), nullable=False),
        sa.Column("grade", sa.Integer(), nullable=False),
        sa.Column("class_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["announcement_id"], ["announcement_record.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["archive_record_id"], ["archive_record.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("announcement_id", "archive_record_id", "class_id", name="uq_announcement_scope_class"),
    )
    op.create_index("ix_announcement_scope_binding_id", "announcement_scope_binding", ["id"])
    op.create_index("ix_announcement_scope_binding_announcement_id", "announcement_scope_binding", ["announcement_id"])
    op.create_index("ix_announcement_scope_binding_archive_record_id", "announcement_scope_binding", ["archive_record_id"])
    op.create_index("ix_announcement_scope_binding_grade", "announcement_scope_binding", ["grade"])
    op.create_index("ix_announcement_scope_binding_class_id", "announcement_scope_binding", ["class_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "announcement_scope_binding" not in inspector.get_table_names():
        return
    indexes = {index["name"] for index in inspector.get_indexes("announcement_scope_binding")}
    for name in (
        "ix_announcement_scope_binding_class_id",
        "ix_announcement_scope_binding_grade",
        "ix_announcement_scope_binding_archive_record_id",
        "ix_announcement_scope_binding_announcement_id",
        "ix_announcement_scope_binding_id",
    ):
        if name in indexes:
            op.drop_index(name, table_name="announcement_scope_binding")
    op.drop_table("announcement_scope_binding")
