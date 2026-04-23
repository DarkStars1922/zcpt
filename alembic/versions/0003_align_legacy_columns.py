"""align legacy sqlite columns with current models

Revision ID: 0003_align_legacy_columns
Revises: 0002_add_file_analysis_result
Create Date: 2026-04-22 16:55:00
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0003_align_legacy_columns"
down_revision = "0002_add_file_analysis_result"
branch_labels = None
depends_on = None


def _get_columns(inspector: sa.Inspector, table_name: str) -> set[str]:
    if table_name not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def _get_indexes(inspector: sa.Inspector, table_name: str) -> set[str]:
    if table_name not in inspector.get_table_names():
        return set()
    return {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    user_columns = _get_columns(inspector, "user_info")
    if "is_reviewer" not in user_columns:
        op.execute("ALTER TABLE user_info ADD COLUMN is_reviewer BOOLEAN NOT NULL DEFAULT 0")
    if "reviewer_token_id" not in user_columns:
        op.execute("ALTER TABLE user_info ADD COLUMN reviewer_token_id INTEGER")
    if "updated_at" not in user_columns:
        op.execute("ALTER TABLE user_info ADD COLUMN updated_at DATETIME")
        op.execute("UPDATE user_info SET updated_at = COALESCE(updated_at, created_at)")

    refresh_columns = _get_columns(inspector, "refresh_token_record")
    if "updated_at" not in refresh_columns:
        op.execute("ALTER TABLE refresh_token_record ADD COLUMN updated_at DATETIME")
        op.execute("UPDATE refresh_token_record SET updated_at = COALESCE(updated_at, created_at)")

    application_columns = _get_columns(inspector, "comprehensive_apply")
    if "award_uid" not in application_columns:
        op.execute("ALTER TABLE comprehensive_apply ADD COLUMN award_uid INTEGER")
        op.execute("UPDATE comprehensive_apply SET award_uid = COALESCE(award_uid, 10001)")
    if "comment" not in application_columns:
        op.execute("ALTER TABLE comprehensive_apply ADD COLUMN comment TEXT")

    inspector = sa.inspect(bind)
    indexes = _get_indexes(inspector, "comprehensive_apply")
    if "ix_comprehensive_apply_award_uid" not in indexes and "award_uid" in _get_columns(inspector, "comprehensive_apply"):
        op.create_index("ix_comprehensive_apply_award_uid", "comprehensive_apply", ["award_uid"], unique=False)


def downgrade() -> None:
    # SQLite 兼容性考虑：不回滚列删除。
    pass
