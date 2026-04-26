"""expand student score summary

Revision ID: 0007_expand_student_score_summary
Revises: 0006_normalize_legacy_local_email_domains
Create Date: 2026-04-26 20:05:00
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "0007_expand_student_score_summary"
down_revision = "0006_normalize_legacy_local_email_domains"
branch_labels = None
depends_on = None


SCORE_RULE_VERSION = "v2_four_categories_two_subtypes"
SCORE_RULES = {
    "physical_mental": {"max_score": 15.0, "sub_types": {"basic": 9.0, "achievement": 6.0}},
    "art": {"max_score": 15.0, "sub_types": {"basic": 9.0, "achievement": 6.0}},
    "labor": {"max_score": 25.0, "sub_types": {"basic": 15.0, "achievement": 10.0}},
    "innovation": {"max_score": 45.0, "sub_types": {"basic": 5.0, "achievement": 40.0}},
}
SUB_FIELDS = [f"{category}_{sub_type}" for category, rule in SCORE_RULES.items() for sub_type in rule["sub_types"]]
CATEGORY_FIELDS = [f"{category}_score" for category in SCORE_RULES]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "student_score_summary" in table_names:
        columns = {column["name"] for column in inspector.get_columns("student_score_summary")}
        for name in (*SUB_FIELDS, *CATEGORY_FIELDS, "raw_total_score", "overflow_score"):
            if name not in columns:
                op.add_column(
                    "student_score_summary",
                    sa.Column(name, sa.Float(), nullable=False, server_default="0"),
                )
        if "score_rule_version" not in columns:
            op.add_column(
                "student_score_summary",
                sa.Column("score_rule_version", sa.String(length=32), nullable=False, server_default=SCORE_RULE_VERSION),
            )
        if "score_breakdown_json" not in columns:
            op.add_column("student_score_summary", sa.Column("score_breakdown_json", sa.Text(), nullable=True))

    if "appeal_record" in table_names:
        columns = {column["name"] for column in inspector.get_columns("appeal_record")}
        if "application_id" not in columns:
            op.add_column("appeal_record", sa.Column("application_id", sa.Integer(), nullable=True))
            op.create_index("ix_appeal_record_application_id", "appeal_record", ["application_id"], unique=False)
        if "score_action" not in columns:
            op.add_column("appeal_record", sa.Column("score_action", sa.String(length=32), nullable=True))
        if "adjusted_score" not in columns:
            op.add_column("appeal_record", sa.Column("adjusted_score", sa.Float(), nullable=True))

    if {"comprehensive_apply", "student_score_summary"}.issubset(table_names):
        bind.execute(
            sa.text(
                "UPDATE comprehensive_apply "
                "SET actual_score_recorded = 1 "
                "WHERE status = 'approved' AND actual_score_recorded = 0"
            )
        )
        _rebuild_score_summaries(bind)


def downgrade() -> None:
    pass


def _rebuild_score_summaries(bind) -> None:
    rows = bind.execute(
        sa.text(
            "SELECT applicant_id, category, sub_type, item_score "
            "FROM comprehensive_apply "
            "WHERE is_deleted = 0 "
            "AND actual_score_recorded = 1 "
            "AND status IN ('approved', 'archived')"
        )
    ).fetchall()
    by_student: dict[int, dict[str, float]] = {}
    for row in rows:
        category = row.category
        sub_type = row.sub_type
        if category not in SCORE_RULES or sub_type not in SCORE_RULES[category]["sub_types"]:
            continue
        student_scores = by_student.setdefault(row.applicant_id, {field: 0.0 for field in SUB_FIELDS})
        student_scores[f"{category}_{sub_type}"] += float(row.item_score or 0.0)

    for student_id, raw_scores in by_student.items():
        payload = _calculate(raw_scores)
        existing = bind.execute(
            sa.text("SELECT id FROM student_score_summary WHERE student_id = :student_id"),
            {"student_id": student_id},
        ).first()
        if existing:
            assignments = ", ".join(f"{column} = :{column}" for column in payload)
            bind.execute(
                sa.text(f"UPDATE student_score_summary SET {assignments} WHERE student_id = :student_id"),
                {"student_id": student_id, **payload},
            )
        else:
            columns = ["student_id", *payload.keys(), "created_at", "updated_at"]
            placeholders = [f":{column}" for column in columns]
            bind.execute(
                sa.text(
                    f"INSERT INTO student_score_summary ({', '.join(columns)}) "
                    f"VALUES ({', '.join(placeholders)})"
                ),
                {"student_id": student_id, **payload, "created_at": datetime.now(timezone.utc), "updated_at": datetime.now(timezone.utc)},
            )


def _calculate(raw_scores: dict[str, float]) -> dict:
    values: dict[str, float | str] = {}
    overflow_score = 0.0
    actual_without_overflow = 0.0
    categories = []
    for category, rule in SCORE_RULES.items():
        capped_subtotal = 0.0
        raw_subtotal = 0.0
        sub_items = []
        for sub_type, sub_max_score in rule["sub_types"].items():
            field = f"{category}_{sub_type}"
            raw_score = raw_scores[field]
            score = min(raw_score, sub_max_score)
            sub_overflow = max(raw_score - sub_max_score, 0.0)
            values[field] = _round(score)
            capped_subtotal += score
            raw_subtotal += raw_score
            overflow_score += sub_overflow
            sub_items.append({"sub_type": sub_type, "raw_score": _round(raw_score), "score": _round(score), "overflow_score": _round(sub_overflow)})
        category_score = min(capped_subtotal, rule["max_score"])
        category_overflow = max(capped_subtotal - rule["max_score"], 0.0)
        overflow_score += category_overflow
        actual_without_overflow += category_score
        values[f"{category}_score"] = _round(category_score)
        categories.append(
            {
                "category": category,
                "raw_score": _round(raw_subtotal),
                "score": _round(category_score),
                "overflow_score": _round(category_overflow),
                "sub_types": sub_items,
            }
        )

    values["raw_total_score"] = _round(sum(raw_scores.values()))
    values["overflow_score"] = _round(overflow_score)
    values["actual_score"] = _round(actual_without_overflow + overflow_score)
    values["score_rule_version"] = SCORE_RULE_VERSION
    values["score_breakdown_json"] = json.dumps({"categories": categories}, ensure_ascii=False)
    return values


def _round(value: float) -> float:
    return round(float(value or 0.0), 4)
