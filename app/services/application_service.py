from datetime import datetime, timezone

from sqlalchemy import and_, func, or_, select
from sqlmodel import Session

from app.models.application import Application
from app.models.user import User

EDITABLE_STATUSES = {"pending_ai", "ai_abnormal", "pending_review"}
VIEWABLE_ROLES = {"student", "teacher"}

CATEGORY_NAME_MAP = {
    "moral": "思想道德",
    "intellectual": "学业科研",
}


class ApplicationError(Exception):
    def __init__(self, message: str, code: int = 1000):
        self.message = message
        self.code = code
        super().__init__(message)


def _check_student(user: User) -> None:
    if user.role != "student":
        raise ApplicationError("无权限", 1003)


def _base_my_query(user_id: int):
    return select(Application).where(and_(Application.applicant_id == user_id, Application.is_deleted.is_(False)))


def create_application(db: Session, user: User, payload) -> Application:
    _check_student(user)
    application = Application(
        applicant_id=user.id,
        category=payload.category,
        sub_type=payload.sub_type,
        award_type=payload.award_type,
        award_level=payload.award_level,
        title=payload.title,
        description=payload.description,
        occurred_at=payload.occurred_at,
        status="pending_ai",
        item_score=None,
        total_score=None,
        score_rule_version=None,
    )
    application.set_attachments([item.model_dump() for item in payload.attachments])

    db.add(application)
    db.commit()
    db.refresh(application)
    return application


def list_my_applications(
    db: Session,
    user: User,
    *,
    status: str | None,
    award_type: str | None,
    category: str | None,
    keyword: str | None,
    page: int,
    size: int,
) -> dict:
    _check_student(user)

    conditions = [Application.applicant_id == user.id, Application.is_deleted.is_(False)]
    if status:
        conditions.append(Application.status == status)
    if award_type:
        conditions.append(Application.award_type == award_type)
    if category:
        conditions.append(Application.category == category)
    if keyword:
        like_exp = f"%{keyword}%"
        conditions.append(
            or_(
                Application.title.ilike(like_exp),
                Application.description.ilike(like_exp),
                Application.award_type.ilike(like_exp),
            )
        )

    count_stmt = select(func.count()).select_from(Application).where(and_(*conditions))
    total = db.scalar(count_stmt) or 0

    stmt = (
        select(Application)
        .where(and_(*conditions))
        .order_by(Application.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    rows = db.scalars(stmt).all()

    return {
        "page": page,
        "size": size,
        "total": total,
        "list": [
            {
                "id": row.id,
                "category": row.category,
                "sub_type": row.sub_type,
                "award_type": row.award_type,
                "award_level": row.award_level,
                "title": row.title,
                "status": row.status,
                "item_score": row.item_score,
                "total_score": row.total_score,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ],
    }


def get_my_category_summary(db: Session, user: User, *, term: str | None) -> dict:
    _check_student(user)

    stmt = select(Application).where(
        and_(Application.applicant_id == user.id, Application.is_deleted.is_(False))
    )
    rows = db.scalars(stmt).all()

    category_data: dict[str, dict] = {}
    total_score = 0.0
    for row in rows:
        cat = row.category
        if cat not in category_data:
            category_data[cat] = {
                "category": cat,
                "category_name": CATEGORY_NAME_MAP.get(cat, cat),
                "count": 0,
                "approved": 0,
                "pending": 0,
                "rejected": 0,
                "category_score": 0.0,
            }
        item = category_data[cat]
        item["count"] += 1

        if row.status == "approved":
            item["approved"] += 1
            if row.item_score is not None:
                item["category_score"] += float(row.item_score)
                total_score += float(row.item_score)
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
                "application_id": row.id,
                "title": row.title,
                "status": row.status,
                "item_score": row.item_score,
                "total_score": row.total_score,
            }
            for row in rows
        ],
    }


def get_application_detail(db: Session, user: User, application_id: int) -> Application:
    if user.role not in VIEWABLE_ROLES:
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
    if payload.version != row.version:
        raise ApplicationError("并发冲突（版本不匹配）", 1007)

    row.category = payload.category
    row.sub_type = payload.sub_type
    row.award_type = payload.award_type
    row.award_level = payload.award_level
    row.title = payload.title
    row.description = payload.description
    row.occurred_at = payload.occurred_at
    row.set_attachments([item.model_dump() for item in payload.attachments])

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
