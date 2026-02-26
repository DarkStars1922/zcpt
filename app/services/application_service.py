from datetime import datetime, timezone

from sqlalchemy import and_, select
from sqlmodel import Session

from app.core.config import settings
from app.core.award_uid_scores import AWARD_SCORE_RULE_VERSION, AWARD_UID_SCORE_MAP
from app.models.application import Application
from app.models.user import User

EDITABLE_STATUSES = {"pending_ai", "ai_abnormal", "pending_review"}
VIEWABLE_ROLES = {"student", "teacher", "admin", "reviewer"}


class ApplicationError(Exception):
    def __init__(self, message: str, code: int = 1000):
        self.message = message
        self.code = code
        super().__init__(message)


def _check_student(user: User) -> None:
    if user.role != "student":
        raise ApplicationError("无权限", 1003)


def _resolve_score(award_uid: int, input_score: float | None) -> float | None:
    score_item = AWARD_UID_SCORE_MAP.get(award_uid)
    if score_item is None:
        raise ApplicationError("无效 award_uid", 1000)

    rule_score = score_item.get("score")
    if not isinstance(rule_score, (int, float)):
        return float(input_score) if input_score is not None else None

    score_value = float(rule_score)
    if score_value == 0:
        if input_score is None:
            raise ApplicationError("当前奖项 score=0，必须传入 score", 1001)
        return float(input_score)

    return score_value


def _resolve_initial_status() -> str:
    if settings.ai_audit_enabled:
        return "pending_ai"
    return "pending_review"


def _resolve_legacy_award_fields(category: str, sub_type: str) -> tuple[str, str]:
    return category, sub_type


def create_application(db: Session, user: User, payload) -> Application:
    _check_student(user)
    resolved_score = _resolve_score(payload.award_uid, payload.score)
    legacy_award_type, legacy_award_level = _resolve_legacy_award_fields(
        payload.category,
        payload.sub_type,
    )

    application = Application(
        applicant_id=user.id,
        category=payload.category,
        sub_type=payload.sub_type,
        award_type=legacy_award_type,
        award_level=legacy_award_level,
        award_uid=payload.award_uid,
        title=payload.title,
        description=payload.description,
        occurred_at=payload.occurred_at,
        status=_resolve_initial_status(),
        score=resolved_score,
        score_rule_version=AWARD_SCORE_RULE_VERSION,
    )
    application.set_attachments([item.model_dump() for item in payload.attachments])

    db.add(application)
    db.commit()
    db.refresh(application)
    return application


def get_my_category_summary(db: Session, user: User, *, term: str | None) -> dict:
    _check_student(user)

    stmt = select(Application).where(
        and_(Application.applicant_id == user.id, Application.is_deleted.is_(False))
    )
    rows = db.scalars(stmt).all()

    category_data: dict[tuple[str, str], dict] = {}
    total_score = 0.0
    for row in rows:
        key = (row.category, row.sub_type)
        if key not in category_data:
            category_data[key] = {
                "category": row.category,
                "sub_type": row.sub_type,
                "count": 0,
                "approved": 0,
                "pending": 0,
                "rejected": 0,
                "category_score": 0.0,
            }
        item = category_data[key]
        item["count"] += 1

        if row.status == "approved":
            item["approved"] += 1
            resolved_item_score = row.score
            if resolved_item_score is not None:
                item["category_score"] += resolved_item_score
                total_score += resolved_item_score
        elif row.status == "rejected":
            item["rejected"] += 1
        elif row.status in {"pending_ai", "ai_abnormal", "pending_review"}:
            item["pending"] += 1

    categories = list(category_data.values())
    return {"term": term, "categories": categories, "total_score": round(total_score, 2)}


def get_my_by_category(
    db: Session,
    user: User,
    *,
    category: str,
    sub_type: str | None,
    status: str | None,
    term: str | None,
    page: int,
    size: int,
) -> dict:
    _check_student(user)

    conditions = [
        Application.applicant_id == user.id,
        Application.category == category,
        Application.is_deleted.is_(False),
    ]
    if sub_type:
        conditions.append(Application.sub_type == sub_type)
    if status:
        conditions.append(Application.status == status)

    stmt = (
        select(Application)
        .where(and_(*conditions))
        .order_by(Application.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    rows = db.scalars(stmt).all()

    return {
        "category": category,
        "term": term,
        "list": [
            {
                "uid": row.award_uid,
                "application_id": row.id,
                "title": row.title,
                "status": row.status,
                "score": row.score,
            }
            for row in rows
        ],
    }


def get_application_detail(db: Session, user: User, application_id: int) -> Application:
    can_view = user.role in VIEWABLE_ROLES or bool(user.is_reviewer)
    if not can_view:
        raise ApplicationError("无权限", 1003)

    row = db.get(Application, application_id)
    if not row or row.is_deleted:
        raise ApplicationError("资源不存在", 1002)

    if user.role == "student" and row.applicant_id != user.id:
        raise ApplicationError("无权限", 1003)

    return row


def update_application(db: Session, user: User, application_id: int, payload) -> Application:
    _check_student(user)
    row = db.get(Application, application_id)
    if not row or row.is_deleted:
        raise ApplicationError("资源不存在", 1002)
    if row.applicant_id != user.id:
        raise ApplicationError("无权限", 1003)
    if row.status not in EDITABLE_STATUSES:
        raise ApplicationError("当前状态不允许编辑", 1000)

    resolved_score = _resolve_score(payload.award_uid, payload.score)
    legacy_award_type, legacy_award_level = _resolve_legacy_award_fields(
        payload.category,
        payload.sub_type,
    )

    row.category = payload.category
    row.sub_type = payload.sub_type
    row.award_type = legacy_award_type
    row.award_level = legacy_award_level
    row.award_uid = payload.award_uid
    row.title = payload.title
    row.description = payload.description
    row.occurred_at = payload.occurred_at
    row.set_attachments([item.model_dump() for item in payload.attachments])
    row.score = resolved_score
    row.score_rule_version = AWARD_SCORE_RULE_VERSION

    row.version += 1
    row.updated_at = datetime.now(timezone.utc)

    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def withdraw_application(db: Session, user: User, application_id: int) -> Application:
    _check_student(user)
    row = db.get(Application, application_id)
    if not row or row.is_deleted:
        raise ApplicationError("资源不存在", 1002)
    if row.applicant_id != user.id:
        raise ApplicationError("无权限", 1003)
    if row.status not in EDITABLE_STATUSES:
        raise ApplicationError("当前状态不允许撤回", 1000)

    row.status = "withdrawn"
    row.version += 1
    row.updated_at = datetime.now(timezone.utc)

    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def soft_delete_application(db: Session, user: User, application_id: int) -> None:
    row = db.get(Application, application_id)
    if not row or row.is_deleted:
        raise ApplicationError("资源不存在", 1002)

    if user.role == "student" and row.applicant_id != user.id:
        raise ApplicationError("无权限", 1003)
    if user.role not in {"student", "admin"}:
        raise ApplicationError("无权限", 1003)

    row.is_deleted = True
    row.deleted_at = datetime.now(timezone.utc)
    row.version += 1

    db.add(row)
    db.commit()
