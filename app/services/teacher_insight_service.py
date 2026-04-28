from __future__ import annotations

import json
import logging
import re
import hashlib
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.core.award_catalog import find_award_rule
from app.core.config import settings
from app.core.constants import MANAGE_REVIEW_ROLES
from app.core.score_rules import SCORE_CATEGORY_KEYS, SCORE_CATEGORY_RULES
from app.core.term_utils import apply_datetime_term_filter
from app.core.utils import json_dumps, json_loads, utcnow
from app.models.application import Application
from app.models.teacher_insight_cache import TeacherInsightCache
from app.models.user import User
from app.services.class_service import get_class_grade, get_class_ids_by_grade, is_graduating_class
from app.services.errors import ServiceError
from app.services.score_summary_service import get_student_score_summary_map, serialize_score_summary

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "你是高校综合测评教师端数据分析助手。你只会看到匿名学生编号、班级编号和清洗后的统计摘要。"
    "请帮助老师发现年级/班级层面的参与积极性、模块短板、数据质量问题和需要关照的学生编号。"
    "请保持谨慎、具体、可执行，不把分数低直接等同于学生态度差。"
)

MICRO_SCORE_THRESHOLD = 0.35
MICRO_KEYWORDS = (
    "参与未获奖",
    "未获奖",
    "其他成员",
    "其它成员",
    "其他作者",
    "其它作者",
    "其他名次",
    "其它名次",
    "其他排名",
    "其它排名",
)
PENDING_STATUSES = {"pending_ai", "pending_review", "ai_abnormal"}
CREDITED_STATUSES = {"approved", "archived"}


def analyze_teacher_insights(
    db: Session,
    user: User,
    *,
    grade: int | None,
    class_id: int | None = None,
    class_ids: list[int] | None = None,
    max_risk_students: int = 12,
    force_refresh: bool = False,
) -> dict:
    if user.role not in MANAGE_REVIEW_ROLES:
        raise ServiceError("permission denied", 1003)
    if grade is None:
        raise ServiceError("grade is required", 1001)

    selected_class_ids = _normalize_class_ids(class_ids=class_ids, legacy_class_id=class_id)
    cache_key = _teacher_insight_cache_key(
        term=settings.default_term,
        grade=grade,
        class_ids=selected_class_ids,
        max_risk_students=max_risk_students,
    )
    if not force_refresh:
        cached = _find_teacher_insight_cache(db, cache_key)
        if cached:
            payload = json_loads(cached.result_json, {})
            if isinstance(payload, dict) and payload:
                return _attach_teacher_cache_meta(payload, cached, hit=True)

    result = _build_teacher_insights(
        db,
        grade=grade,
        selected_class_ids=selected_class_ids,
        max_risk_students=max_risk_students,
    )
    _store_teacher_insight_cache(
        db,
        user=user,
        cache_key=cache_key,
        grade=grade,
        class_ids=selected_class_ids,
        max_risk_students=max_risk_students,
        result=result,
    )
    cached = _find_teacher_insight_cache(db, cache_key)
    if cached:
        return _attach_teacher_cache_meta(result, cached, hit=False)
    return {**result, "cache": {"hit": False, "cache_key": cache_key}}


def _build_teacher_insights(
    db: Session,
    *,
    grade: int,
    selected_class_ids: list[int],
    max_risk_students: int,
) -> dict:
    students = _query_students(db, grade=grade, class_ids=selected_class_ids)
    if not students:
        return _empty_result(grade=grade, class_ids=selected_class_ids)

    student_ids = [student.id for student in students if student.id is not None]
    applications = _query_term_applications(db, student_ids)
    cleaned_by_application_id = {application.id: _clean_application(application) for application in applications}
    applications_by_student: dict[int, list[Application]] = defaultdict(list)
    for application in applications:
        applications_by_student[application.applicant_id].append(application)

    score_summary_map = get_student_score_summary_map(db, student_ids)
    student_rows = []
    identity_map = {}
    for index, student in enumerate(students, start=1):
        code = f"S{index:04d}"
        summary = serialize_score_summary(score_summary_map.get(student.id), student_id=student.id)
        row = _build_student_row(
            code=code,
            student=student,
            score_summary=summary,
            applications=applications_by_student.get(student.id or -1, []),
            cleaned_by_application_id=cleaned_by_application_id,
            db=db,
        )
        student_rows.append(row)
        identity_map[code] = {
            "student_id": student.id,
            "student_account": student.account,
            "student_name": student.name,
            "class_id": student.class_id,
            "grade": row["grade"],
        }

    aggregate = _build_aggregate(
        student_rows,
        applications,
        cleaned_by_application_id,
        grade=grade,
        selected_class_ids=selected_class_ids,
    )
    risk_candidates = _pick_risk_candidates(student_rows, limit=120)
    prompt_payload = {
        "term": settings.default_term,
        "scope": aggregate["scope"],
        "metrics": aggregate["metrics"],
        "module_findings": aggregate["module_findings"],
        "class_summaries": _anonymous_class_summaries(aggregate["class_findings"]),
        "key_category_summary": aggregate["key_category_summary"],
        "data_quality": aggregate["data_quality"],
        "risk_candidates": [_anonymous_candidate(row) for row in risk_candidates],
        "output_limit": max_risk_students,
    }

    llm_result = _call_llm(prompt_payload)
    if not llm_result:
        llm_result = _build_rule_result(aggregate, risk_candidates, max_risk_students=max_risk_students)

    enriched = _enrich_result(
        llm_result,
        aggregate=aggregate,
        identity_map=identity_map,
        student_rows=student_rows,
        max_risk_students=max_risk_students,
    )
    return {
        "term": settings.default_term,
        "scope": aggregate["scope"],
        "generated_at": utcnow().isoformat(),
        "source": enriched["source"],
        "status": enriched["status"],
        "summary": enriched["summary"],
        "overall_risk_level": enriched["overall_risk_level"],
        "metrics": aggregate["metrics"],
        "data_quality": aggregate["data_quality"],
        "module_findings": enriched["module_findings"],
        "class_findings": enriched["class_findings"],
        "key_category_summary": aggregate["key_category_summary"],
        "risk_students": enriched["risk_students"],
        "action_plan": enriched["action_plan"],
        "model": enriched.get("model"),
    }


def _teacher_insight_cache_key(*, term: str, grade: int, class_ids: list[int], max_risk_students: int) -> str:
    class_key = _teacher_insight_class_ids_key(class_ids)
    raw = f"{term}|{grade}|{class_key}|{max_risk_students}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _teacher_insight_class_ids_key(class_ids: list[int]) -> str:
    if not class_ids:
        return "ALL"
    return ",".join(str(item) for item in sorted(set(int(value) for value in class_ids)))


def _find_teacher_insight_cache(db: Session, cache_key: str) -> TeacherInsightCache | None:
    return db.exec(select(TeacherInsightCache).where(TeacherInsightCache.cache_key == cache_key)).first()


def _store_teacher_insight_cache(
    db: Session,
    *,
    user: User,
    cache_key: str,
    grade: int,
    class_ids: list[int],
    max_risk_students: int,
    result: dict,
) -> None:
    now = utcnow()
    existing = _find_teacher_insight_cache(db, cache_key)
    if existing:
        existing.result_json = json_dumps(result)
        existing.source = result.get("source")
        existing.status = result.get("status") or "completed"
        existing.generated_by = user.id
        existing.generated_at = now
        existing.updated_at = now
        db.add(existing)
    else:
        db.add(
            TeacherInsightCache(
                cache_key=cache_key,
                term=settings.default_term,
                grade=grade,
                class_ids_key=_teacher_insight_class_ids_key(class_ids),
                max_risk_students=max_risk_students,
                result_json=json_dumps(result),
                source=result.get("source"),
                status=result.get("status") or "completed",
                generated_by=user.id,
                generated_at=now,
                updated_at=now,
            )
        )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()


def _attach_teacher_cache_meta(result: dict, cache: TeacherInsightCache, *, hit: bool) -> dict:
    payload = {**result}
    payload["cache"] = {
        "hit": hit,
        "cache_id": cache.id,
        "cache_key": cache.cache_key,
        "generated_at": cache.generated_at.isoformat() if cache.generated_at else payload.get("generated_at"),
        "term": cache.term,
        "status": cache.status,
    }
    return payload


def _normalize_class_ids(*, class_ids: list[int] | None, legacy_class_id: int | None) -> list[int]:
    values = []
    if class_ids:
        values.extend(class_ids)
    if legacy_class_id:
        values.append(legacy_class_id)
    result = []
    for value in values:
        try:
            int_value = int(value)
        except (TypeError, ValueError):
            continue
        if int_value not in result:
            result.append(int_value)
    return result


def _query_students(db: Session, *, grade: int, class_ids: list[int]) -> list[User]:
    grade_class_ids = get_class_ids_by_grade(db, grade, include_graduating=False)
    if class_ids:
        allowed_class_ids = [class_id for class_id in class_ids if class_id in grade_class_ids]
    else:
        allowed_class_ids = grade_class_ids
    stmt = select(User).where(User.role == "student", User.is_deleted.is_(False))
    stmt = stmt.where(User.class_id.in_(allowed_class_ids) if allowed_class_ids else User.class_id == -1)
    rows = db.exec(stmt.order_by(User.class_id.asc(), User.account.asc())).all()
    return [row for row in rows if not is_graduating_class(db, row.class_id)]


def _query_term_applications(db: Session, student_ids: list[int]) -> list[Application]:
    if not student_ids:
        return []
    stmt = select(Application).where(
        Application.applicant_id.in_(student_ids),
        Application.is_deleted.is_(False),
    )
    stmt = apply_datetime_term_filter(stmt, Application.created_at, settings.default_term)
    return db.exec(stmt).all()


def _clean_application(application: Application) -> dict:
    rule = find_award_rule(application.award_uid)
    category = application.category or (rule or {}).get("category")
    sub_type = application.sub_type or (rule or {}).get("sub_type")
    rule_path = (rule or {}).get("rule_path") or (rule or {}).get("rule_name") or ""
    rule_name = (rule or {}).get("rule_name") or rule_path or "未知规则"
    segments = _path_segments(rule_path or rule_name)
    detail_segments = segments[2:] if len(segments) >= 3 else _path_segments(rule_name)
    key_category = detail_segments[0] if detail_segments else rule_name
    leaf = detail_segments[-1] if detail_segments else rule_name
    score = float(application.item_score or 0.0)
    text = " / ".join([rule_name, rule_path, leaf])
    is_micro = score <= MICRO_SCORE_THRESHOLD or any(keyword in text for keyword in MICRO_KEYWORDS)
    return {
        "application_id": application.id,
        "award_uid": application.award_uid,
        "category": category,
        "sub_type": sub_type,
        "score": _round(score),
        "status": application.status,
        "credited": application.status in CREDITED_STATUSES and bool(application.actual_score_recorded),
        "rule_path": rule_path,
        "rule_name": rule_name,
        "path_segments": segments,
        "key_category": key_category,
        "event_level": _detect_event_level(detail_segments),
        "award_level": _detect_award_level(detail_segments),
        "participation_role": _detect_participation_role(detail_segments),
        "project_type": _detect_project_type(detail_segments),
        "is_micro": is_micro,
        "quality_bucket": "micro_activity" if is_micro else "meaningful_activity",
    }


def _build_student_row(
    *,
    code: str,
    student: User,
    score_summary: dict,
    applications: list[Application],
    cleaned_by_application_id: dict[int | None, dict],
    db: Session,
) -> dict:
    status_count = defaultdict(int)
    category_count = defaultdict(int)
    meaningful_count = 0
    micro_count = 0
    credited_count = 0
    meaningful_achievement_count = 0
    credited_meaningful_count = 0
    key_categories = set()
    key_category_counter = Counter()
    category_quality = {
        category: {"raw": 0, "meaningful": 0, "micro": 0, "credited": 0}
        for category in SCORE_CATEGORY_KEYS
    }
    for application in applications:
        cleaned = cleaned_by_application_id.get(application.id) or _clean_application(application)
        status_count[application.status] += 1
        category = cleaned["category"]
        if category in SCORE_CATEGORY_RULES:
            category_count[category] += 1
            category_quality[category]["raw"] += 1
            if cleaned["credited"]:
                category_quality[category]["credited"] += 1
        if cleaned["credited"]:
            credited_count += 1
        if cleaned["is_micro"]:
            micro_count += 1
            if category in SCORE_CATEGORY_RULES:
                category_quality[category]["micro"] += 1
        else:
            meaningful_count += 1
            if category in SCORE_CATEGORY_RULES:
                category_quality[category]["meaningful"] += 1
            if cleaned["score"] > 0:
                key_categories.add(cleaned["key_category"])
                key_category_counter[cleaned["key_category"]] += 1
            if cleaned["credited"]:
                credited_meaningful_count += 1
            if cleaned["sub_type"] == "achievement" and cleaned["credited"]:
                meaningful_achievement_count += 1

    categories = _extract_score_categories(score_summary)
    risk = _score_student_risk(
        total_score=float(score_summary.get("actual_score") or 0.0),
        raw_application_count=len(applications),
        meaningful_count=meaningful_count,
        micro_count=micro_count,
        credited_count=credited_count,
        meaningful_achievement_count=meaningful_achievement_count,
        status_count=status_count,
        categories=categories,
        key_category_count=len(key_categories),
    )
    return {
        "student_code": code,
        "student_id": student.id,
        "grade": get_class_grade(db, student.class_id),
        "class_id": student.class_id,
        "raw_application_count": len(applications),
        "application_count": len(applications),
        "credited_count": credited_count,
        "meaningful_count": meaningful_count,
        "credited_meaningful_count": credited_meaningful_count,
        "micro_count": micro_count,
        "micro_ratio": _safe_ratio(micro_count, len(applications)),
        "pending_count": sum(status_count[item] for item in PENDING_STATUSES),
        "rejected_count": status_count["rejected"],
        "approved_count": status_count["approved"] + status_count["archived"],
        "actual_score": float(score_summary.get("actual_score") or 0.0),
        "raw_total_score": float(score_summary.get("raw_total_score") or 0.0),
        "overflow_score": float(score_summary.get("overflow_score") or 0.0),
        "achievement_total": sum(payload["achievement"] for payload in categories.values()),
        "meaningful_achievement_count": meaningful_achievement_count,
        "key_category_count": len(key_categories),
        "key_category_top": _counter_top(key_category_counter, limit=5),
        "category_count": dict(category_count),
        "category_quality": category_quality,
        "categories": categories,
        "risk_score": risk["score"],
        "risk_reasons": risk["reasons"],
    }


def _extract_score_categories(score_summary: dict) -> dict:
    categories = {}
    for category in score_summary.get("categories") or []:
        key = category.get("category")
        if not key:
            continue
        achievement = 0.0
        basic = 0.0
        achievement_overflow = 0.0
        for sub in category.get("sub_types") or []:
            if sub.get("sub_type") == "basic":
                basic = float(sub.get("score") or 0.0)
            elif sub.get("sub_type") == "achievement":
                achievement = float(sub.get("score") or 0.0)
                achievement_overflow = float(sub.get("overflow_score") or 0.0)
        categories[key] = {
            "score": float(category.get("score") or 0.0),
            "max_score": float(category.get("max_score") or SCORE_CATEGORY_RULES.get(key, {}).get("max_score") or 0.0),
            "basic": basic,
            "achievement": achievement,
            "overflow": float(category.get("achievement_overflow_score") or category.get("overflow_score") or achievement_overflow),
        }
    for key, rule in SCORE_CATEGORY_RULES.items():
        categories.setdefault(
            key,
            {"score": 0.0, "max_score": float(rule["max_score"]), "basic": 0.0, "achievement": 0.0, "overflow": 0.0},
        )
    return categories


def _score_student_risk(
    *,
    total_score: float,
    raw_application_count: int,
    meaningful_count: int,
    micro_count: int,
    credited_count: int,
    meaningful_achievement_count: int,
    status_count: dict,
    categories: dict,
    key_category_count: int,
) -> dict:
    score = 0
    reasons = []
    if raw_application_count == 0:
        score += 60
        reasons.append("本学期暂无申报记录")
    elif meaningful_count == 0:
        score += 36
        reasons.append("申报多为微分或参与痕迹，缺少有效成果")
    elif meaningful_count <= 1:
        score += 22
        reasons.append("有效申报次数偏少")
    if credited_count == 0:
        score += 28
        reasons.append("暂无已入账申报")
    if total_score <= 5:
        score += 28
        reasons.append("官方总分处于低位")
    elif total_score <= 20:
        score += 16
        reasons.append("官方总分低于常规活跃水平")
    if raw_application_count >= 5 and _safe_ratio(micro_count, raw_application_count) >= 0.6:
        score += 16
        reasons.append("微分条目占比较高，可能污染活跃度判断")
    if meaningful_achievement_count <= 0 and raw_application_count > 0:
        score += 14
        reasons.append("成果/突破类有效入账暂为空")
    if key_category_count <= 1 and meaningful_count >= 2:
        score += 8
        reasons.append("有效申报类别较集中，模块覆盖不足")
    weak_modules = []
    for key, payload in categories.items():
        max_score = max(float(payload.get("max_score") or 1.0), 1.0)
        ratio = float(payload.get("score") or 0.0) / max_score
        if ratio < 0.12:
            weak_modules.append(SCORE_CATEGORY_RULES.get(key, {}).get("name", key))
    if weak_modules:
        score += min(len(weak_modules) * 4, 14)
        reasons.append(f"{'、'.join(weak_modules[:3])}分布偏弱")
    if int(status_count.get("rejected", 0)) >= 2:
        score += 8
        reasons.append("驳回记录偏多，需关注材料规范")
    if sum(int(status_count.get(item, 0)) for item in PENDING_STATUSES) >= 3:
        score += 5
        reasons.append("待处理申报较多，建议及时跟进")
    return {"score": score, "reasons": reasons or ["暂无明显风险"]}


def _build_aggregate(
    student_rows: list[dict],
    applications: list[Application],
    cleaned_by_application_id: dict[int | None, dict],
    *,
    grade: int,
    selected_class_ids: list[int],
) -> dict:
    class_ids = sorted({row["class_id"] for row in student_rows if row["class_id"] is not None})
    scope = {
        "grade": grade,
        "class_ids": selected_class_ids,
        "resolved_class_ids": class_ids,
        "label": _scope_label(grade, selected_class_ids or class_ids),
    }
    metrics = _build_metrics(student_rows)
    module_findings = _build_module_findings(student_rows)
    key_category_summary = _build_key_category_summary(applications, cleaned_by_application_id)
    class_findings = [
        _build_class_finding(class_id, [row for row in student_rows if row["class_id"] == class_id])
        for class_id in class_ids
    ]
    data_quality = {
        "micro_count": metrics["micro_count"],
        "micro_ratio": metrics["micro_ratio"],
        "meaningful_count": metrics["meaningful_count"],
        "raw_application_count": metrics["raw_application_count"],
        "note": _data_quality_note(metrics),
    }
    return {
        "scope": scope,
        "metrics": metrics,
        "module_findings": module_findings,
        "class_findings": class_findings,
        "key_category_summary": key_category_summary,
        "data_quality": data_quality,
        "application_status_summary": dict(_count_status(applications)),
    }


def _build_metrics(student_rows: list[dict]) -> dict:
    student_count = len(student_rows)
    raw_application_count = sum(row["raw_application_count"] for row in student_rows)
    meaningful_count = sum(row["meaningful_count"] for row in student_rows)
    micro_count = sum(row["micro_count"] for row in student_rows)
    credited_count = sum(row["credited_count"] for row in student_rows)
    total_score = sum(row["actual_score"] for row in student_rows)
    return {
        "student_count": student_count,
        "raw_application_count": raw_application_count,
        "application_count": raw_application_count,
        "credited_count": credited_count,
        "credited_application_count": credited_count,
        "meaningful_count": meaningful_count,
        "micro_count": micro_count,
        "micro_ratio": _safe_ratio(micro_count, raw_application_count),
        "average_score": _round(total_score / student_count) if student_count else 0.0,
        "total_score": _round(total_score),
        "application_per_student": _round(raw_application_count / student_count) if student_count else 0.0,
        "meaningful_per_student": _round(meaningful_count / student_count) if student_count else 0.0,
        "no_application_count": sum(1 for row in student_rows if row["raw_application_count"] == 0),
        "no_meaningful_count": sum(1 for row in student_rows if row["meaningful_count"] == 0),
        "no_achievement_count": sum(1 for row in student_rows if row["meaningful_achievement_count"] == 0),
        "high_micro_ratio_count": sum(1 for row in student_rows if row["raw_application_count"] >= 3 and row["micro_ratio"] >= 0.6),
        "low_score_count": sum(1 for row in student_rows if row["actual_score"] <= 20),
        "pending_count": sum(row["pending_count"] for row in student_rows),
        "rejected_count": sum(row["rejected_count"] for row in student_rows),
    }


def _build_module_findings(student_rows: list[dict]) -> list[dict]:
    student_count = len(student_rows)
    result = []
    for category in SCORE_CATEGORY_KEYS:
        rule = SCORE_CATEGORY_RULES[category]
        score_sum = sum(row["categories"].get(category, {}).get("score", 0.0) for row in student_rows)
        basic_sum = sum(row["categories"].get(category, {}).get("basic", 0.0) for row in student_rows)
        achievement_sum = sum(row["categories"].get(category, {}).get("achievement", 0.0) for row in student_rows)
        raw_count = sum(row["category_quality"].get(category, {}).get("raw", 0) for row in student_rows)
        meaningful_count = sum(row["category_quality"].get(category, {}).get("meaningful", 0) for row in student_rows)
        micro_count = sum(row["category_quality"].get(category, {}).get("micro", 0) for row in student_rows)
        average_ratio = _safe_ratio(score_sum, student_count * float(rule["max_score"])) if student_count else 0.0
        result.append(
            {
                "category": category,
                "module": rule["name"],
                "name": rule["name"],
                "max_score": rule["max_score"],
                "average_score": _round(score_sum / student_count) if student_count else 0.0,
                "average_ratio": average_ratio,
                "basic_average": _round(basic_sum / student_count) if student_count else 0.0,
                "achievement_average": _round(achievement_sum / student_count) if student_count else 0.0,
                "raw_application_count": raw_count,
                "meaningful_count": meaningful_count,
                "micro_count": micro_count,
                "micro_ratio": _safe_ratio(micro_count, raw_count),
                "application_per_student": _round(raw_count / student_count) if student_count else 0.0,
                "meaningful_per_student": _round(meaningful_count / student_count) if student_count else 0.0,
                "activity_level": _activity_level(average_ratio, _safe_ratio(meaningful_count, student_count), _safe_ratio(micro_count, raw_count)),
            }
        )
    return result


def _build_key_category_summary(applications: list[Application], cleaned_by_application_id: dict[int | None, dict]) -> dict:
    meaningful_counter = Counter()
    micro_counter = Counter()
    module_counter: dict[str, Counter] = defaultdict(Counter)
    for application in applications:
        cleaned = cleaned_by_application_id.get(application.id) or _clean_application(application)
        key = f"{SCORE_CATEGORY_RULES.get(cleaned['category'], {}).get('name', cleaned['category'])} / {cleaned['key_category']}"
        if cleaned["is_micro"]:
            micro_counter[key] += 1
        else:
            meaningful_counter[key] += 1
        if cleaned["category"] in SCORE_CATEGORY_RULES:
            module_counter[cleaned["category"]][cleaned["key_category"]] += 1
    return {
        "meaningful_top": _counter_top(meaningful_counter, limit=8),
        "micro_top": _counter_top(micro_counter, limit=8),
        "by_module": {
            SCORE_CATEGORY_RULES[category]["name"]: _counter_top(counter, limit=5)
            for category, counter in module_counter.items()
            if category in SCORE_CATEGORY_RULES
        },
    }


def _build_class_finding(class_id: int, rows: list[dict]) -> dict:
    metrics = _build_metrics(rows)
    module_findings = _build_module_findings(rows)
    weak_modules = [
        item["module"]
        for item in sorted(module_findings, key=lambda item: (item["average_ratio"], item["meaningful_per_student"]))
        if item["activity_level"] == "低"
    ][:2]
    risk_level = _risk_level_from_metrics(metrics)
    summary = (
        f"{class_id}班共{metrics['student_count']}人，人均官方分{metrics['average_score']}，"
        f"人均有效申报{metrics['meaningful_per_student']}条，微分条目占比{_percent(metrics['micro_ratio'])}。"
    )
    if weak_modules:
        summary += f" 需重点关注{'、'.join(weak_modules)}。"
    return {
        "class_id": class_id,
        "grade": _single_value([row["grade"] for row in rows]),
        "label": f"{class_id}班",
        "summary": summary,
        "risk_level": risk_level,
        "metrics": metrics,
        "module_findings": module_findings,
        "focus_modules": weak_modules,
        "suggestion": _class_suggestion(metrics, weak_modules),
    }


def _anonymous_class_summaries(class_findings: list[dict]) -> list[dict]:
    result = []
    for item in class_findings:
        result.append(
            {
                "class_id": item["class_id"],
                "metrics": item["metrics"],
                "module_findings": item["module_findings"],
                "focus_modules": item["focus_modules"],
            }
        )
    return result


def _pick_risk_candidates(student_rows: list[dict], *, limit: int) -> list[dict]:
    return sorted(student_rows, key=lambda row: (-row["risk_score"], row["actual_score"], row["student_code"]))[:limit]


def _anonymous_candidate(row: dict) -> dict:
    return {
        "student_code": row["student_code"],
        "grade": row["grade"],
        "class_id": row["class_id"],
        "raw_application_count": row["raw_application_count"],
        "credited_count": row["credited_count"],
        "meaningful_count": row["meaningful_count"],
        "micro_count": row["micro_count"],
        "micro_ratio": row["micro_ratio"],
        "pending_count": row["pending_count"],
        "rejected_count": row["rejected_count"],
        "official_score": _round(row["actual_score"]),
        "raw_score": _round(row["raw_total_score"]),
        "overflow_score": _round(row["overflow_score"]),
        "meaningful_achievement_count": row["meaningful_achievement_count"],
        "key_category_count": row["key_category_count"],
        "key_category_top": row["key_category_top"],
        "risk_reasons": row["risk_reasons"],
        "module_scores": {
            category: {
                "score": _round(payload.get("score", 0.0)),
                "basic": _round(payload.get("basic", 0.0)),
                "achievement": _round(payload.get("achievement", 0.0)),
                "overflow": _round(payload.get("overflow", 0.0)),
            }
            for category, payload in row["categories"].items()
        },
    }


def _call_llm(prompt_payload: dict) -> dict | None:
    api_url = settings.teacher_analysis_llm_api_url or settings.report_story_llm_api_url or settings.evaluation_llm_api_url
    api_key = settings.teacher_analysis_llm_api_key or settings.report_story_llm_api_key or settings.evaluation_llm_api_key
    model = settings.teacher_analysis_llm_model or settings.report_story_llm_model or settings.evaluation_llm_model
    if not api_url or not api_key:
        return None

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_prompt(prompt_payload)},
        ],
        "temperature": settings.teacher_analysis_llm_temperature,
        "max_tokens": settings.teacher_analysis_llm_max_tokens,
    }
    try:
        with httpx.Client(timeout=settings.teacher_analysis_llm_timeout_seconds) as client:
            response = client.post(
                api_url,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        parsed = _extract_json_object(_extract_content(data))
        parsed["source"] = "llm"
        parsed["status"] = "completed"
        parsed["model"] = model
        return parsed
    except Exception as exc:
        logger.warning("teacher insight llm request failed: %s", exc)
        return None


def _build_prompt(payload: dict) -> str:
    return (
        "请分析以下高校综合测评当前学期清洗后数据，输出严格JSON对象，不要Markdown，不要额外解释。\n"
        "隐私规则：输入中没有学生姓名或学号。你只能引用 student_code，例如 S0001；不要猜测姓名、性别、家庭、心理状态。\n"
        "数据口径：raw_application_count 是原始申报数；meaningful_count 是清洗后的有效条目；micro_count 是微分/参与未获奖/其他成员等低价值条目。"
        "大量 micro_count 只能说明参与痕迹，不代表高质量活跃。基础类参与和成果/突破类获奖必须分开判断。\n"
        "分析目标：输出整体画像、各班级分项画像、四个素养模块积极性、需要关注的匿名学生编号、数据质量提醒和行动建议。\n"
        "module_findings 必须覆盖身心素养、文艺素养、劳动素养、创新素养四项，observation 必须写出具体数据。\n"
        "class_findings 必须覆盖输入里的每个 class_id，说明该班级的主要问题或优势。\n"
        "返回结构：\n"
        "{\n"
        '  "summary": "180字以内整体画像",\n'
        '  "overall_risk_level": "low|medium|high",\n'
        '  "module_findings": [{"module": "身心素养", "activity_level": "低|中|高", "observation": "事实观察", "suggestion": "建议"}],\n'
        '  "class_findings": [{"class_id": 301, "summary": "班级画像", "risk_level": "low|medium|high", "focus_modules": ["文艺素养"], "suggestion": "建议"}],\n'
        '  "risk_students": [{"student_code": "S0001", "risk_level": "low|medium|high", "risk_type": "参与不足/模块失衡/成果不足/材料规范/微分污染/待处理积压", "evidence": "证据", "suggestion": "老师可采取的提醒方式"}],\n'
        '  "data_quality_notes": ["数据质量提醒"],\n'
        '  "action_plan": ["具体行动1", "具体行动2", "具体行动3"]\n'
        "}\n"
        "risk_students 最多返回 output_limit 个，优先选择证据充分的学生编号。\n\n"
        f"清洗后匿名数据：{json.dumps(payload, ensure_ascii=False)}"
    )


def _build_rule_result(aggregate: dict, risk_candidates: list[dict], *, max_risk_students: int) -> dict:
    metrics = aggregate["metrics"]
    modules = []
    for item in aggregate["module_findings"]:
        modules.append(
            {
                "module": item["module"],
                "activity_level": item["activity_level"],
                "observation": (
                    f"平均得分{item['average_score']}分，人均有效申报{item['meaningful_per_student']}条，"
                    f"微分占比{_percent(item['micro_ratio'])}。"
                ),
                "suggestion": _module_suggestion(item["category"], item["activity_level"], item["micro_ratio"]),
            }
        )
    return {
        "source": "rule",
        "status": "fallback",
        "summary": (
            f"当前范围共有{metrics['student_count']}名学生，人均官方总分{metrics['average_score']}分，"
            f"人均有效申报{metrics['meaningful_per_student']}条，微分条目占比{_percent(metrics['micro_ratio'])}。"
            f"暂无申报{metrics['no_application_count']}人，有效成果/突破为空{metrics['no_achievement_count']}人。"
        ),
        "overall_risk_level": _risk_level_from_metrics(metrics),
        "module_findings": modules,
        "class_findings": aggregate["class_findings"],
        "risk_students": [
            {
                "student_code": row["student_code"],
                "risk_level": "high" if row["risk_score"] >= 70 else "medium" if row["risk_score"] >= 38 else "low",
                "risk_type": _risk_type(row),
                "evidence": "；".join(row["risk_reasons"][:3]),
                "suggestion": "建议先确认活动参与、材料准备和填报理解情况，再给出定向提醒。",
            }
            for row in risk_candidates[:max_risk_students]
        ],
        "data_quality_notes": [_data_quality_note(metrics)],
        "action_plan": [
            "先按班级查看微分占比和有效申报数，避免被大量低分参与条目误导。",
            "对积极性偏弱的模块开展一次定向机会推送，并明确对应证明材料要求。",
            "对暂无申报、有效成果为空或待处理积压的学生做一对一提醒。",
        ],
    }


def _enrich_result(
    llm_result: dict,
    *,
    aggregate: dict,
    identity_map: dict,
    student_rows: list[dict],
    max_risk_students: int,
) -> dict:
    row_by_code = {row["student_code"]: row for row in student_rows}
    return {
        "source": llm_result.get("source") or "rule",
        "status": llm_result.get("status") or "completed",
        "model": llm_result.get("model"),
        "summary": llm_result.get("summary") or _build_rule_result(aggregate, [], max_risk_students=0)["summary"],
        "overall_risk_level": llm_result.get("overall_risk_level") or _risk_level_from_metrics(aggregate["metrics"]),
        "module_findings": _merge_module_findings(aggregate["module_findings"], llm_result.get("module_findings")),
        "class_findings": _merge_class_findings(aggregate["class_findings"], llm_result.get("class_findings")),
        "risk_students": _enrich_risk_students(
            llm_result.get("risk_students") or [],
            identity_map=identity_map,
            row_by_code=row_by_code,
            max_risk_students=max_risk_students,
        )
        or _fallback_risk_students(row_by_code, identity_map=identity_map, max_risk_students=max_risk_students),
        "action_plan": _normalize_string_list(llm_result.get("action_plan"))
        or _build_rule_result(aggregate, [], max_risk_students=0)["action_plan"],
    }


def _merge_module_findings(base_items: list[dict], llm_items: Any) -> list[dict]:
    by_name = {}
    if isinstance(llm_items, list):
        for item in llm_items:
            if isinstance(item, dict):
                name = str(item.get("module") or item.get("name") or "")
                if name:
                    by_name[name] = item
    result = []
    for base in base_items:
        override = by_name.get(base["module"]) or {}
        result.append(
            {
                **base,
                "activity_level": override.get("activity_level") or base.get("activity_level") or "中",
                "observation": override.get("observation")
                or (
                    f"平均得分{base['average_score']}分，人均有效申报{base['meaningful_per_student']}条，"
                    f"微分占比{_percent(base['micro_ratio'])}。"
                ),
                "suggestion": override.get("suggestion") or _module_suggestion(base["category"], base.get("activity_level"), base.get("micro_ratio", 0.0)),
            }
        )
    return result


def _merge_class_findings(base_items: list[dict], llm_items: Any) -> list[dict]:
    by_class_id = {}
    if isinstance(llm_items, list):
        for item in llm_items:
            if not isinstance(item, dict):
                continue
            try:
                class_id = int(item.get("class_id"))
            except (TypeError, ValueError):
                continue
            by_class_id[class_id] = item
    result = []
    for base in base_items:
        override = by_class_id.get(base["class_id"]) or {}
        focus_modules = override.get("focus_modules") if isinstance(override.get("focus_modules"), list) else base["focus_modules"]
        result.append(
            {
                **base,
                "summary": override.get("summary") or base["summary"],
                "risk_level": override.get("risk_level") or base["risk_level"],
                "focus_modules": focus_modules,
                "suggestion": override.get("suggestion") or base["suggestion"],
            }
        )
    return result


def _enrich_risk_students(
    llm_items: list,
    *,
    identity_map: dict,
    row_by_code: dict,
    max_risk_students: int,
) -> list[dict]:
    result = []
    for item in llm_items:
        if not isinstance(item, dict):
            continue
        code = str(item.get("student_code") or "").strip()
        identity = identity_map.get(code)
        if not identity:
            continue
        row = row_by_code.get(code, {})
        result.append(
            {
                "student_code": code,
                "student": identity,
                "risk_level": item.get("risk_level") or ("high" if row.get("risk_score", 0) >= 70 else "medium"),
                "risk_type": item.get("risk_type") or _risk_type(row),
                "evidence": item.get("evidence") or "；".join((row.get("risk_reasons") or [])[:3]),
                "suggestion": item.get("suggestion") or "建议老师结合申报明细进一步核实。",
                "metrics": {
                    "official_score": _round(row.get("actual_score", 0.0)),
                    "raw_application_count": row.get("raw_application_count", 0),
                    "application_count": row.get("raw_application_count", 0),
                    "meaningful_count": row.get("meaningful_count", 0),
                    "micro_count": row.get("micro_count", 0),
                    "micro_ratio": row.get("micro_ratio", 0.0),
                    "credited_count": row.get("credited_count", 0),
                    "pending_count": row.get("pending_count", 0),
                    "rejected_count": row.get("rejected_count", 0),
                },
            }
        )
    return result[:max_risk_students]


def _fallback_risk_students(row_by_code: dict, *, identity_map: dict, max_risk_students: int) -> list[dict]:
    rows = sorted(row_by_code.values(), key=lambda row: (-row.get("risk_score", 0), row.get("actual_score", 0.0), row.get("student_code", "")))
    result = []
    for row in rows[:max_risk_students]:
        code = row.get("student_code")
        identity = identity_map.get(code)
        if not identity:
            continue
        result.append(
            {
                "student_code": code,
                "student": identity,
                "risk_level": "high" if row.get("risk_score", 0) >= 70 else "medium" if row.get("risk_score", 0) >= 38 else "low",
                "risk_type": _risk_type(row),
                "evidence": "；".join((row.get("risk_reasons") or [])[:3]),
                "suggestion": "建议老师结合申报明细进一步核实。",
                "metrics": {
                    "official_score": _round(row.get("actual_score", 0.0)),
                    "raw_application_count": row.get("raw_application_count", 0),
                    "application_count": row.get("raw_application_count", 0),
                    "meaningful_count": row.get("meaningful_count", 0),
                    "micro_count": row.get("micro_count", 0),
                    "micro_ratio": row.get("micro_ratio", 0.0),
                    "credited_count": row.get("credited_count", 0),
                    "pending_count": row.get("pending_count", 0),
                    "rejected_count": row.get("rejected_count", 0),
                },
            }
        )
    return result


def _extract_content(data: dict) -> str:
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0] or {}
        message = first.get("message") or {}
        content = message.get("content") or first.get("text")
        if isinstance(content, str):
            return content
    content = data.get("content")
    return content if isinstance(content, str) else ""


def _normalize_string_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()][:8]


def _extract_json_object(content: str) -> dict:
    if not content:
        raise ValueError("empty llm response")
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            raise
        payload = json.loads(match.group(0))
    if not isinstance(payload, dict):
        raise ValueError("llm response must be object")
    return payload


def _path_segments(value: str) -> list[str]:
    return [segment.strip() for segment in str(value or "").split("/") if segment.strip()]


def _detect_event_level(segments: list[str]) -> str:
    text = " / ".join(segments)
    for keyword in ("国家级", "国家", "省级", "校级", "书院级", "院级", "国际", "A(A*)级", "A-", "B(B*)级", "C级", "D级", "E级"):
        if keyword in text:
            return keyword
    return "未标明"


def _detect_award_level(segments: list[str]) -> str:
    text = " / ".join(segments)
    for keyword in ("一等奖", "二等奖", "三等奖", "第一名", "第二名", "第三名", "优秀奖", "参与未获奖"):
        if keyword in text:
            return keyword
    return "未标明"


def _detect_participation_role(segments: list[str]) -> str:
    text = " / ".join(segments)
    for keyword in ("第一作者", "第二作者", "其他作者", "第一发明人", "前三位成员", "其他成员", "其它成员", "个人", "集体"):
        if keyword in text:
            return keyword
    return "未标明"


def _detect_project_type(segments: list[str]) -> str:
    text = " / ".join(segments)
    if "个人" in text:
        return "个人项目"
    if "集体" in text or "团队" in text:
        return "集体项目"
    return "未标明"


def _counter_top(counter: Counter, *, limit: int) -> list[dict]:
    return [{"name": str(name), "count": int(count)} for name, count in counter.most_common(limit)]


def _count_status(applications: list[Application]) -> dict:
    counter = defaultdict(int)
    for application in applications:
        counter[application.status] += 1
    return counter


def _single_value(values: list) -> int | None:
    unique = {value for value in values if value is not None}
    return next(iter(unique)) if len(unique) == 1 else None


def _scope_label(grade: int, class_ids: list[int]) -> str:
    if class_ids:
        return f"{grade}级 " + "、".join(f"{class_id}班" for class_id in class_ids)
    return f"{grade}级全部班级"


def _activity_level(score_ratio: float, meaningful_per_student: float, micro_ratio: float) -> str:
    if meaningful_per_student < 0.35 or score_ratio < 0.12:
        return "低"
    if meaningful_per_student >= 1.2 and score_ratio >= 0.36 and micro_ratio < 0.5:
        return "高"
    return "中"


def _risk_level_from_metrics(metrics: dict) -> str:
    if metrics.get("no_application_count", 0) or metrics.get("micro_ratio", 0.0) >= 0.55:
        return "high"
    if metrics.get("low_score_count", 0) or metrics.get("no_meaningful_count", 0):
        return "medium"
    return "low"


def _risk_type(row: dict) -> str:
    reasons = " ".join(row.get("risk_reasons") or [])
    if "微分" in reasons:
        return "微分污染"
    if "暂无申报" in reasons or "有效申报次数偏少" in reasons:
        return "参与不足"
    if "成果" in reasons:
        return "成果不足"
    if "驳回" in reasons:
        return "材料规范"
    if "覆盖不足" in reasons or "分布偏弱" in reasons:
        return "模块失衡"
    return "待关注"


def _module_suggestion(category: str, level: str | None, micro_ratio: float = 0.0) -> str:
    if micro_ratio >= 0.55:
        return "建议先区分参与痕迹与高质量成果，避免大量微分条目掩盖真实短板。"
    if level != "低":
        return "保持现有活动供给，继续提醒学生及时留存证明并按时申报。"
    suggestions = {
        "physical_mental": "可以增加体育集体活动提醒，帮助学生把参与证明及时转化为申报记录。",
        "art": "可以集中推送讲座、展演和社团实践机会，降低学生参与门槛。",
        "labor": "可以围绕志愿服务、社会实践和宿舍劳动建立周期性提醒。",
        "innovation": "可以为竞赛、科研训练和创新项目提供更清晰的报名与材料指引。",
    }
    return suggestions.get(category, "建议开展定向提醒并复盘活动供给。")


def _class_suggestion(metrics: dict, weak_modules: list[str]) -> str:
    if metrics["micro_ratio"] >= 0.55:
        return "该班微分条目占比较高，建议先做材料与规则口径说明，再引导学生关注更有效的成果类申报。"
    if weak_modules:
        return f"建议围绕{'、'.join(weak_modules)}补充活动机会和申报指引。"
    return "该班整体暂无明显集中短板，建议维持常规提醒并跟进未申报学生。"


def _data_quality_note(metrics: dict) -> str:
    if metrics.get("micro_ratio", 0.0) >= 0.55:
        return "微分/参与痕迹条目占比较高，分析时已降低其对积极性的权重。"
    if metrics.get("micro_count", 0):
        return "存在少量微分/参与痕迹条目，已单独统计，不与成果类高价值申报混算。"
    return "当前范围内暂未发现明显微分条目污染。"


def _empty_result(*, grade: int, class_ids: list[int]) -> dict:
    return {
        "term": settings.default_term,
        "scope": {"grade": grade, "class_ids": class_ids, "resolved_class_ids": [], "label": _scope_label(grade, class_ids)},
        "generated_at": datetime.now().isoformat(),
        "source": "rule",
        "status": "empty",
        "summary": "当前筛选范围内暂无可分析学生。",
        "overall_risk_level": "low",
        "metrics": _build_metrics([]),
        "data_quality": {"micro_count": 0, "micro_ratio": 0.0, "meaningful_count": 0, "raw_application_count": 0, "note": "当前没有可分析数据。"},
        "module_findings": [],
        "class_findings": [],
        "key_category_summary": {"meaningful_top": [], "micro_top": [], "by_module": {}},
        "risk_students": [],
        "action_plan": [],
    }


def _safe_ratio(numerator: float, denominator: float) -> float:
    return _round(float(numerator or 0.0) / float(denominator or 1.0)) if denominator else 0.0


def _percent(value: float) -> str:
    return f"{round(float(value or 0.0) * 100, 1)}%"


def _round(value) -> float:
    return round(float(value or 0.0), 4)
