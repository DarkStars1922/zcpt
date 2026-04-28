"""add report and insight cache tables

Revision ID: 0012_add_report_and_insight_cache
Revises: 0011_add_classes_and_appeal_anonymous
Create Date: 2026-04-28 00:10:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0012_add_report_and_insight_cache"
down_revision = "0011_add_classes_and_appeal_anonymous"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "student_report_cache" not in table_names:
        op.create_table(
            "student_report_cache",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("announcement_id", sa.Integer(), nullable=False),
            sa.Column("student_id", sa.Integer(), nullable=False),
            sa.Column("term", sa.String(length=32), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="completed"),
            sa.Column("report_json", sa.Text(), nullable=False),
            sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["announcement_id"], ["announcement_record.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["student_id"], ["user_info.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("announcement_id", "student_id", name="uq_student_report_cache_scope"),
        )
        op.create_index("ix_student_report_cache_id", "student_report_cache", ["id"])
        op.create_index("ix_student_report_cache_announcement_id", "student_report_cache", ["announcement_id"])
        op.create_index("ix_student_report_cache_student_id", "student_report_cache", ["student_id"])
        op.create_index("ix_student_report_cache_term", "student_report_cache", ["term"])
        op.create_index("ix_student_report_cache_status", "student_report_cache", ["status"])
        op.create_index("ix_student_report_cache_generated_at", "student_report_cache", ["generated_at"])

    if "teacher_insight_cache" not in table_names:
        op.create_table(
            "teacher_insight_cache",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("cache_key", sa.String(length=64), nullable=False),
            sa.Column("term", sa.String(length=32), nullable=False),
            sa.Column("grade", sa.Integer(), nullable=False),
            sa.Column("class_ids_key", sa.String(length=512), nullable=False),
            sa.Column("max_risk_students", sa.Integer(), nullable=False, server_default="12"),
            sa.Column("result_json", sa.Text(), nullable=False),
            sa.Column("source", sa.String(length=32), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="completed"),
            sa.Column("generated_by", sa.Integer(), nullable=True),
            sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["generated_by"], ["user_info.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_teacher_insight_cache_id", "teacher_insight_cache", ["id"])
        op.create_index("ix_teacher_insight_cache_cache_key", "teacher_insight_cache", ["cache_key"], unique=True)
        op.create_index("ix_teacher_insight_cache_term", "teacher_insight_cache", ["term"])
        op.create_index("ix_teacher_insight_cache_grade", "teacher_insight_cache", ["grade"])
        op.create_index("ix_teacher_insight_cache_class_ids_key", "teacher_insight_cache", ["class_ids_key"])
        op.create_index("ix_teacher_insight_cache_source", "teacher_insight_cache", ["source"])
        op.create_index("ix_teacher_insight_cache_status", "teacher_insight_cache", ["status"])
        op.create_index("ix_teacher_insight_cache_generated_at", "teacher_insight_cache", ["generated_at"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "teacher_insight_cache" in table_names:
        indexes = {index["name"] for index in inspector.get_indexes("teacher_insight_cache")}
        for name in (
            "ix_teacher_insight_cache_generated_at",
            "ix_teacher_insight_cache_status",
            "ix_teacher_insight_cache_source",
            "ix_teacher_insight_cache_class_ids_key",
            "ix_teacher_insight_cache_grade",
            "ix_teacher_insight_cache_term",
            "ix_teacher_insight_cache_cache_key",
            "ix_teacher_insight_cache_id",
        ):
            if name in indexes:
                op.drop_index(name, table_name="teacher_insight_cache")
        op.drop_table("teacher_insight_cache")

    if "student_report_cache" in table_names:
        indexes = {index["name"] for index in inspector.get_indexes("student_report_cache")}
        for name in (
            "ix_student_report_cache_generated_at",
            "ix_student_report_cache_status",
            "ix_student_report_cache_term",
            "ix_student_report_cache_student_id",
            "ix_student_report_cache_announcement_id",
            "ix_student_report_cache_id",
        ):
            if name in indexes:
                op.drop_index(name, table_name="student_report_cache")
        op.drop_table("student_report_cache")
