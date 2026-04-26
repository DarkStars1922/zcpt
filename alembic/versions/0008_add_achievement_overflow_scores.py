"""add achievement overflow scores

Revision ID: 0008_add_achievement_overflow_scores
Revises: 0007_expand_student_score_summary
Create Date: 2026-04-26 21:15:00
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "0008_add_achievement_overflow_scores"
down_revision = "0007_expand_student_score_summary"
branch_labels = None
depends_on = None


OVERFLOW_FIELDS = (
    "physical_mental_achievement_overflow",
    "art_achievement_overflow",
    "labor_achievement_overflow",
    "innovation_achievement_overflow",
)
SCORE_RULE_VERSION = "v2_four_categories_two_subtypes"
SCORE_RULES = {
    "physical_mental": {
        "name": "身心素养",
        "max_score": 15.0,
        "sub_types": {
            "basic": {"name": "基础性评价", "max_score": 9.0},
            "achievement": {"name": "成果性评价", "max_score": 6.0},
        },
    },
    "art": {
        "name": "文艺素养",
        "max_score": 15.0,
        "sub_types": {
            "basic": {"name": "基础性评价", "max_score": 9.0},
            "achievement": {"name": "成果性评价", "max_score": 6.0},
        },
    },
    "labor": {
        "name": "劳动素养",
        "max_score": 25.0,
        "sub_types": {
            "basic": {"name": "基础性评价", "max_score": 15.0},
            "achievement": {"name": "成果性评价", "max_score": 10.0},
        },
    },
    "innovation": {
        "name": "创新素养",
        "max_score": 45.0,
        "sub_types": {
            "basic": {"name": "基础素养", "max_score": 5.0},
            "achievement": {"name": "突破提升", "max_score": 40.0},
        },
    },
}
SUB_FIELDS = [f"{category}_{sub_type}" for category, rule in SCORE_RULES.items() for sub_type in rule["sub_types"]]
CATEGORY_FIELDS = [f"{category}_score" for category in SCORE_RULES]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "student_score_summary" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("student_score_summary")}
    for field in OVERFLOW_FIELDS:
        if field not in columns:
            op.add_column(
                "student_score_summary",
                sa.Column(field, sa.Float(), nullable=False, server_default="0"),
            )
    if "comprehensive_apply" in inspector.get_table_names():
        _rebuild_score_summaries(bind)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "student_score_summary" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("student_score_summary")}
    for field in reversed(OVERFLOW_FIELDS):
        if field in columns:
            op.drop_column("student_score_summary", field)


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
                {
                    "student_id": student_id,
                    **payload,
                    "created_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc),
                },
            )


def _calculate(raw_scores: dict[str, float]) -> dict:
    values: dict[str, float | str] = {}
    overflow_score = 0.0
    actual_score = 0.0
    categories = []
    for category, rule in SCORE_RULES.items():
        capped_subtotal = 0.0
        raw_subtotal = 0.0
        achievement_overflow = 0.0
        sub_items = []
        for sub_type, sub_rule in rule["sub_types"].items():
            field = f"{category}_{sub_type}"
            raw_score = raw_scores[field]
            max_score = float(sub_rule["max_score"])
            score = min(raw_score, max_score)
            sub_overflow = max(raw_score - max_score, 0.0) if sub_type == "achievement" else 0.0
            values[field] = _round(score)
            capped_subtotal += score
            raw_subtotal += raw_score
            achievement_overflow += sub_overflow
            sub_items.append(
                {
                    "sub_type": sub_type,
                    "sub_type_name": sub_rule["name"],
                    "max_score": max_score,
                    "raw_score": _round(raw_score),
                    "score": _round(score),
                    "overflow_score": _round(sub_overflow),
                }
            )
        category_score = min(capped_subtotal, float(rule["max_score"]))
        values[f"{category}_score"] = _round(category_score)
        values[f"{category}_achievement_overflow"] = _round(achievement_overflow)
        overflow_score += achievement_overflow
        actual_score += category_score
        categories.append(
            {
                "category": category,
                "category_name": rule["name"],
                "max_score": rule["max_score"],
                "raw_score": _round(raw_subtotal),
                "score": _round(category_score),
                "overflow_score": _round(achievement_overflow),
                "achievement_overflow_score": _round(achievement_overflow),
                "sub_types": sub_items,
            }
        )

    values["raw_total_score"] = _round(sum(raw_scores.values()))
    values["overflow_score"] = _round(overflow_score)
    values["actual_score"] = _round(actual_score)
    values["score_rule_version"] = SCORE_RULE_VERSION
    values["score_breakdown_json"] = json.dumps({"categories": categories}, ensure_ascii=False)
    return values


def _round(value: float) -> float:
    return round(float(value or 0.0), 4)
