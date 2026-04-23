"""add student score summary and actual score flag

Revision ID: 0005_add_student_score_summary_and_actual_flag
Revises: 0004_rebuild_comprehensive_apply_table
Create Date: 2026-04-23 09:30:00
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0005_add_student_score_summary_and_actual_flag"
down_revision = "0004_rebuild_comprehensive_apply_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "comprehensive_apply" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("comprehensive_apply")}
        if "actual_score_recorded" not in columns:
            op.add_column(
                "comprehensive_apply",
                sa.Column("actual_score_recorded", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            )
            op.create_index(
                "ix_comprehensive_apply_actual_score_recorded",
                "comprehensive_apply",
                ["actual_score_recorded"],
                unique=False,
            )

    if "student_score_summary" not in inspector.get_table_names():
        op.create_table(
            "student_score_summary",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("student_id", sa.Integer(), nullable=False),
            sa.Column("actual_score", sa.Float(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["student_id"], ["user_info.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("student_id", name="uq_student_score_summary_student_id"),
        )
        op.create_index("ix_student_score_summary_id", "student_score_summary", ["id"], unique=False)
        op.create_index("ix_student_score_summary_student_id", "student_score_summary", ["student_id"], unique=False)


def downgrade() -> None:
    pass
