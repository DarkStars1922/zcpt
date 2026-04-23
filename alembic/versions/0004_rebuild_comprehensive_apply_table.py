"""rebuild comprehensive_apply legacy table to current schema

Revision ID: 0004_rebuild_comprehensive_apply_table
Revises: 0003_align_legacy_columns
Create Date: 2026-04-22 17:10:00
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0004_rebuild_comprehensive_apply_table"
down_revision = "0003_align_legacy_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_name = "comprehensive_apply"
    if table_name not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns(table_name)}
    legacy_columns = {"award_type", "award_level", "attachments_json"}
    if not (columns & legacy_columns):
        return

    op.execute("PRAGMA foreign_keys=OFF")

    op.create_table(
        "comprehensive_apply_new",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("applicant_id", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("sub_type", sa.String(length=64), nullable=False),
        sa.Column("award_uid", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("item_score", sa.Float(), nullable=True),
        sa.Column("total_score", sa.Float(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("score_rule_version", sa.String(length=32), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["applicant_id"], ["user_info.id"], ondelete="CASCADE"),
    )

    award_uid_expr = "COALESCE(award_uid, 10001)" if "award_uid" in columns else "10001"
    comment_expr = "comment" if "comment" in columns else "NULL"

    op.execute(
        f"""
        INSERT INTO comprehensive_apply_new (
          id, applicant_id, category, sub_type, award_uid, title, description, occurred_at,
          status, item_score, total_score, comment, score_rule_version, version, is_deleted,
          created_at, updated_at, deleted_at
        )
        SELECT
          id, applicant_id, category, sub_type, {award_uid_expr}, title, description, occurred_at,
          status, item_score, total_score, {comment_expr}, score_rule_version, version, is_deleted,
          created_at, updated_at, deleted_at
        FROM comprehensive_apply
        """
    )

    op.drop_table("comprehensive_apply")
    op.rename_table("comprehensive_apply_new", "comprehensive_apply")

    op.create_index("ix_comprehensive_apply_id", "comprehensive_apply", ["id"], unique=False)
    op.create_index("ix_comprehensive_apply_applicant_id", "comprehensive_apply", ["applicant_id"], unique=False)
    op.create_index("ix_comprehensive_apply_category", "comprehensive_apply", ["category"], unique=False)
    op.create_index("ix_comprehensive_apply_sub_type", "comprehensive_apply", ["sub_type"], unique=False)
    op.create_index("ix_comprehensive_apply_award_uid", "comprehensive_apply", ["award_uid"], unique=False)
    op.create_index("ix_comprehensive_apply_status", "comprehensive_apply", ["status"], unique=False)
    op.create_index("ix_comprehensive_apply_is_deleted", "comprehensive_apply", ["is_deleted"], unique=False)

    op.execute("PRAGMA foreign_keys=ON")


def downgrade() -> None:
    # 历史库兼容改造，避免做破坏性回滚。
    pass
