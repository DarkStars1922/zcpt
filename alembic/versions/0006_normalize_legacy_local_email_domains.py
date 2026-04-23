"""normalize legacy .local email domains

Revision ID: 0006_normalize_legacy_local_email_domains
Revises: 0005_add_student_score_summary_and_actual_flag
Create Date: 2026-04-23 18:10:00
"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0006_normalize_legacy_local_email_domains"
down_revision = "0005_add_student_score_summary_and_actual_flag"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "user_info" in table_names:
        rows = bind.execute(
            sa.text("SELECT id, email FROM user_info WHERE email IS NOT NULL")
        ).fetchall()
        for row in rows:
            email = (row.email or "").strip()
            normalized = _normalize_local_domain(email)
            if normalized and normalized != email:
                bind.execute(
                    sa.text("UPDATE user_info SET email = :email WHERE id = :id"),
                    {"id": row.id, "email": normalized},
                )

    if "system_config" in table_names:
        row = bind.execute(
            sa.text("SELECT id, config_value_json FROM system_config WHERE config_key = :key"),
            {"key": "email"},
        ).first()
        if row:
            payload = _load_json(row.config_value_json)
            default_from = payload.get("default_from")
            if isinstance(default_from, str):
                normalized_from = _normalize_local_domain(default_from.strip())
                if normalized_from and normalized_from != default_from:
                    payload["default_from"] = normalized_from
                    bind.execute(
                        sa.text("UPDATE system_config SET config_value_json = :payload WHERE id = :id"),
                        {"id": row.id, "payload": json.dumps(payload, ensure_ascii=False)},
                    )


def downgrade() -> None:
    pass


def _normalize_local_domain(value: str) -> str | None:
    if not value:
        return None
    if value.lower().endswith(".local") and "@" in value:
        return f"{value[:-6]}.example.com"
    return value


def _load_json(value: str | None) -> dict:
    if not value:
        return {}
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}
