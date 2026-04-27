from __future__ import annotations

from sqlmodel import Session, select

from app.core.config import settings
from app.core.score_rules import (
    SCORE_CATEGORY_FIELD_KEYS,
    SCORE_CATEGORY_KEYS,
    SCORE_CATEGORY_RULES,
    SCORE_ACHIEVEMENT_OVERFLOW_FIELD_KEYS,
    SCORE_RULE_VERSION,
    SCORE_SUB_FIELD_KEYS,
    SCORE_SUB_TYPE_KEYS,
    is_valid_score_category,
)
from app.core.term_utils import apply_datetime_term_filter
from app.core.utils import json_dumps, json_loads, utcnow
from app.models.application import Application
from app.models.student_score_summary import StudentScoreSummary


def get_student_actual_score_map(db: Session, student_ids: list[int]) -> dict[int, float]:
    if not student_ids:
        return {}
    rows = db.exec(
        select(StudentScoreSummary).where(StudentScoreSummary.student_id.in_(list(dict.fromkeys(student_ids))))
    ).all()
    return {row.student_id: float(row.actual_score or 0.0) for row in rows}


def get_student_score_summary_map(db: Session, student_ids: list[int]) -> dict[int, StudentScoreSummary]:
    if not student_ids:
        return {}
    rows = db.exec(
        select(StudentScoreSummary).where(StudentScoreSummary.student_id.in_(list(dict.fromkeys(student_ids))))
    ).all()
    return {row.student_id: row for row in rows}


def get_student_score_summary(db: Session, student_id: int) -> StudentScoreSummary | None:
    return db.exec(select(StudentScoreSummary).where(StudentScoreSummary.student_id == student_id)).first()


def get_or_create_student_score_summary(db: Session, student_id: int) -> StudentScoreSummary:
    summary = get_student_score_summary(db, student_id)
    if summary:
        return summary
    summary = StudentScoreSummary(student_id=student_id)
    db.add(summary)
    db.flush()
    return summary


def recalculate_student_score(
    db: Session,
    student_id: int,
    *,
    auto_commit: bool = False,
) -> StudentScoreSummary:
    stmt = select(Application).where(
        Application.applicant_id == student_id,
        Application.status.in_(("approved", "archived")),
        Application.actual_score_recorded.is_(True),
        Application.is_deleted.is_(False),
    )
    stmt = apply_datetime_term_filter(stmt, Application.created_at, settings.default_term)
    rows = db.exec(stmt).all()
    values = calculate_score_values(rows)
    summary = get_or_create_student_score_summary(db, student_id)
    _apply_score_values(summary, values)
    db.add(summary)
    if auto_commit:
        db.commit()
        db.refresh(summary)
    return summary


def recalculate_students_score(db: Session, student_ids: list[int]) -> list[StudentScoreSummary]:
    summaries = []
    for student_id in dict.fromkeys(student_ids):
        summaries.append(recalculate_student_score(db, student_id))
    return summaries


def mark_application_score_recorded(application: Application) -> None:
    application.actual_score_recorded = application.status == "approved"


def mark_application_archived_score_recorded(application: Application, previous_status: str) -> None:
    application.actual_score_recorded = previous_status == "approved"


def calculate_score_values(applications: list[Application]) -> dict:
    raw_sub_scores = {field: 0.0 for field in SCORE_SUB_FIELD_KEYS}
    ignored_applications: list[int] = []

    for application in applications:
        if not is_valid_score_category(application.category, application.sub_type):
            if application.id is not None:
                ignored_applications.append(application.id)
            continue
        field = _sub_score_field(application.category, application.sub_type)
        raw_sub_scores[field] += float(application.item_score or 0.0)

    sub_scores: dict[str, float] = {}
    category_scores: dict[str, float] = {}
    category_raw_scores: dict[str, float] = {}
    category_overflow_scores: dict[str, float] = {}
    achievement_overflow_scores: dict[str, float] = {}
    overflow_score = 0.0
    official_total_score = 0.0

    for category in SCORE_CATEGORY_KEYS:
        rule = SCORE_CATEGORY_RULES[category]
        capped_subtotal = 0.0
        raw_subtotal = 0.0
        achievement_overflow = 0.0
        for sub_type in SCORE_SUB_TYPE_KEYS:
            sub_field = _sub_score_field(category, sub_type)
            raw_score = raw_sub_scores[sub_field]
            sub_max_score = float(rule["sub_types"][sub_type]["max_score"])
            sub_score = min(raw_score, sub_max_score)
            if sub_type == "achievement":
                achievement_overflow += max(raw_score - sub_max_score, 0.0)
            raw_subtotal += raw_score
            capped_subtotal += sub_score
            sub_scores[sub_field] = _round_score(sub_score)

        category_max_score = float(rule["max_score"])
        category_score = min(capped_subtotal, category_max_score)
        category_raw_scores[category] = _round_score(raw_subtotal)
        category_overflow_scores[category] = _round_score(achievement_overflow)
        achievement_overflow_scores[f"{category}_achievement_overflow"] = _round_score(achievement_overflow)
        category_scores[f"{category}_score"] = _round_score(category_score)
        overflow_score += achievement_overflow
        official_total_score += category_score

    raw_total_score = sum(raw_sub_scores.values())
    overflow_score = _round_score(overflow_score)
    actual_score = _round_score(official_total_score)

    return {
        **sub_scores,
        **category_scores,
        **achievement_overflow_scores,
        "raw_total_score": _round_score(raw_total_score),
        "overflow_score": overflow_score,
        "actual_score": actual_score,
        "score_rule_version": SCORE_RULE_VERSION,
        "score_breakdown_json": json_dumps(
            _build_score_breakdown(
                raw_sub_scores=raw_sub_scores,
                sub_scores=sub_scores,
                category_scores=category_scores,
                category_raw_scores=category_raw_scores,
                category_overflow_scores=category_overflow_scores,
                achievement_overflow_scores=achievement_overflow_scores,
                ignored_applications=ignored_applications,
            )
        ),
    }


def serialize_score_summary(summary: StudentScoreSummary | None, *, student_id: int | None = None) -> dict:
    if summary is None:
        return _empty_serialized_summary(student_id)
    breakdown = json_loads(summary.score_breakdown_json, {})
    categories = breakdown.get("categories")
    if not categories:
        categories = _build_serialized_categories_from_summary(summary)
    return {
        "student_id": summary.student_id,
        "raw_total_score": _round_score(summary.raw_total_score),
        "overflow_score": _round_score(summary.overflow_score),
        "actual_score": _round_score(summary.actual_score),
        "score_rule_version": summary.score_rule_version,
        "sub_scores": {
            field: _round_score(getattr(summary, field, 0.0))
            for field in SCORE_SUB_FIELD_KEYS
        },
        "category_scores": {
            field: _round_score(getattr(summary, field, 0.0))
            for field in SCORE_CATEGORY_FIELD_KEYS
        },
        "achievement_overflow_scores": {
            field: _round_score(getattr(summary, field, 0.0))
            for field in SCORE_ACHIEVEMENT_OVERFLOW_FIELD_KEYS
        },
        "categories": categories,
        "updated_at": summary.updated_at.isoformat() if summary.updated_at else None,
    }


def _apply_score_values(summary: StudentScoreSummary, values: dict) -> None:
    for field in (*SCORE_SUB_FIELD_KEYS, *SCORE_CATEGORY_FIELD_KEYS, *SCORE_ACHIEVEMENT_OVERFLOW_FIELD_KEYS):
        setattr(summary, field, values.get(field, 0.0))
    summary.raw_total_score = values["raw_total_score"]
    summary.overflow_score = values["overflow_score"]
    summary.actual_score = values["actual_score"]
    summary.score_rule_version = values["score_rule_version"]
    summary.score_breakdown_json = values["score_breakdown_json"]
    summary.updated_at = utcnow()


def _build_score_breakdown(
    *,
    raw_sub_scores: dict[str, float],
    sub_scores: dict[str, float],
    category_scores: dict[str, float],
    category_raw_scores: dict[str, float],
    category_overflow_scores: dict[str, float],
    achievement_overflow_scores: dict[str, float],
    ignored_applications: list[int],
) -> dict:
    categories = []
    for category in SCORE_CATEGORY_KEYS:
        rule = SCORE_CATEGORY_RULES[category]
        categories.append(
            {
                "category": category,
                "category_name": rule["name"],
                "max_score": rule["max_score"],
                "raw_score": category_raw_scores[category],
                "score": category_scores[f"{category}_score"],
                "overflow_score": category_overflow_scores[category],
                "achievement_overflow_score": achievement_overflow_scores[f"{category}_achievement_overflow"],
                "sub_types": [
                    {
                        "sub_type": sub_type,
                        "sub_type_name": rule["sub_types"][sub_type]["name"],
                        "max_score": rule["sub_types"][sub_type]["max_score"],
                        "raw_score": _round_score(raw_sub_scores[_sub_score_field(category, sub_type)]),
                        "score": sub_scores[_sub_score_field(category, sub_type)],
                        "overflow_score": _round_score(
                            max(
                                raw_sub_scores[_sub_score_field(category, sub_type)]
                                - float(rule["sub_types"][sub_type]["max_score"]),
                                0.0,
                            )
                            if sub_type == "achievement"
                            else 0.0
                        ),
                    }
                    for sub_type in SCORE_SUB_TYPE_KEYS
                ],
            }
        )
    return {
        "categories": categories,
        "ignored_application_ids": ignored_applications,
    }


def _empty_serialized_summary(student_id: int | None) -> dict:
    return {
        "student_id": student_id,
        "raw_total_score": 0.0,
        "overflow_score": 0.0,
        "actual_score": 0.0,
        "score_rule_version": SCORE_RULE_VERSION,
        "sub_scores": {field: 0.0 for field in SCORE_SUB_FIELD_KEYS},
        "category_scores": {field: 0.0 for field in SCORE_CATEGORY_FIELD_KEYS},
        "achievement_overflow_scores": {field: 0.0 for field in SCORE_ACHIEVEMENT_OVERFLOW_FIELD_KEYS},
        "categories": _build_score_breakdown(
            raw_sub_scores={field: 0.0 for field in SCORE_SUB_FIELD_KEYS},
            sub_scores={field: 0.0 for field in SCORE_SUB_FIELD_KEYS},
            category_scores={field: 0.0 for field in SCORE_CATEGORY_FIELD_KEYS},
            category_raw_scores={category: 0.0 for category in SCORE_CATEGORY_KEYS},
            category_overflow_scores={category: 0.0 for category in SCORE_CATEGORY_KEYS},
            achievement_overflow_scores={field: 0.0 for field in SCORE_ACHIEVEMENT_OVERFLOW_FIELD_KEYS},
            ignored_applications=[],
        )["categories"],
        "updated_at": None,
    }


def _build_serialized_categories_from_summary(summary: StudentScoreSummary) -> list[dict]:
    raw_sub_scores = {}
    sub_scores = {}
    category_scores = {}
    category_raw_scores = {}
    category_overflow_scores = {}
    achievement_overflow_scores = {}

    for category in SCORE_CATEGORY_KEYS:
        achievement_overflow_field = f"{category}_achievement_overflow"
        achievement_overflow = _round_score(getattr(summary, achievement_overflow_field, 0.0))
        achievement_overflow_scores[achievement_overflow_field] = achievement_overflow
        category_overflow_scores[category] = achievement_overflow

        raw_subtotal = 0.0
        for sub_type in SCORE_SUB_TYPE_KEYS:
            sub_field = _sub_score_field(category, sub_type)
            score = _round_score(getattr(summary, sub_field, 0.0))
            raw_score = score + achievement_overflow if sub_type == "achievement" else score
            raw_sub_scores[sub_field] = _round_score(raw_score)
            sub_scores[sub_field] = score
            raw_subtotal += raw_score

        category_score_field = f"{category}_score"
        category_scores[category_score_field] = _round_score(getattr(summary, category_score_field, 0.0))
        category_raw_scores[category] = _round_score(raw_subtotal)

    return _build_score_breakdown(
        raw_sub_scores=raw_sub_scores,
        sub_scores=sub_scores,
        category_scores=category_scores,
        category_raw_scores=category_raw_scores,
        category_overflow_scores=category_overflow_scores,
        achievement_overflow_scores=achievement_overflow_scores,
        ignored_applications=[],
    )["categories"]


def _sub_score_field(category: str, sub_type: str) -> str:
    return f"{category}_{sub_type}"


def _round_score(value: float | None) -> float:
    return round(float(value or 0.0), 4)
