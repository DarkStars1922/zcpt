"""add classes and appeal anonymous flag

Revision ID: 0011_add_classes_and_appeal_anonymous
Revises: 0010_add_announcement_scope_binding
Create Date: 2026-04-27 04:20:00
"""

from __future__ import annotations

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "0011_add_classes_and_appeal_anonymous"
down_revision = "0010_add_announcement_scope_binding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "class_info" not in table_names:
        op.create_table(
            "class_info",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("class_id", sa.Integer(), nullable=False),
            sa.Column("grade", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=64), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("class_id", name="uq_class_info_class_id"),
        )
        op.create_index("ix_class_info_id", "class_info", ["id"])
        op.create_index("ix_class_info_class_id", "class_info", ["class_id"])
        op.create_index("ix_class_info_grade", "class_info", ["grade"])
        op.create_index("ix_class_info_is_active", "class_info", ["is_active"])
        op.create_index("ix_class_info_is_deleted", "class_info", ["is_deleted"])

        class_table = sa.table(
            "class_info",
            sa.column("class_id", sa.Integer()),
            sa.column("grade", sa.Integer()),
            sa.column("name", sa.String()),
            sa.column("created_at", sa.DateTime(timezone=True)),
            sa.column("updated_at", sa.DateTime(timezone=True)),
        )
        now = datetime.now(timezone.utc)
        op.bulk_insert(
            class_table,
            [
                {"class_id": 301, "grade": 2023, "name": "2023级 301班", "created_at": now, "updated_at": now},
                {"class_id": 302, "grade": 2023, "name": "2023级 302班", "created_at": now, "updated_at": now},
                {"class_id": 303, "grade": 2023, "name": "2023级 303班", "created_at": now, "updated_at": now},
            ],
        )

    appeal_columns = {column["name"] for column in inspector.get_columns("appeal_record")}
    if "is_anonymous" not in appeal_columns:
        op.add_column(
            "appeal_record",
            sa.Column("is_anonymous", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        op.create_index("ix_appeal_record_is_anonymous", "appeal_record", ["is_anonymous"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "appeal_record" in table_names:
        appeal_columns = {column["name"] for column in inspector.get_columns("appeal_record")}
        if "is_anonymous" in appeal_columns:
            indexes = {index["name"] for index in inspector.get_indexes("appeal_record")}
            if "ix_appeal_record_is_anonymous" in indexes:
                op.drop_index("ix_appeal_record_is_anonymous", table_name="appeal_record")
            op.drop_column("appeal_record", "is_anonymous")

    if "class_info" in table_names:
        indexes = {index["name"] for index in inspector.get_indexes("class_info")}
        for name in (
            "ix_class_info_is_deleted",
            "ix_class_info_is_active",
            "ix_class_info_grade",
            "ix_class_info_class_id",
            "ix_class_info_id",
        ):
            if name in indexes:
                op.drop_index(name, table_name="class_info")
        op.drop_table("class_info")
