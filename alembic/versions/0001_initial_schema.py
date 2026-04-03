"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-04-02 23:20:00
"""

from alembic import op
from sqlmodel import SQLModel

import app.models  # noqa: F401

# revision identifiers, used by Alembic.
revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    SQLModel.metadata.create_all(bind=bind)


def downgrade() -> None:
    bind = op.get_bind()
    SQLModel.metadata.drop_all(bind=bind)
