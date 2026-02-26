from datetime import datetime, timezone
from dataclasses import dataclass

from sqlalchemy import and_, or_, select
from sqlmodel import Session

from app.models.application import Application
from app.models.review_record import ReviewRecord
from app.models.reviewer_token import ReviewerToken
from app.models.user import User

REVIEWER_REVIEWABLE_STATUSES = {"pending_review", "ai_abnormal"}
TEACHER_REVIEWABLE_STATUSES = {"pending_teacher"}


@dataclass
class ReviewActorContext:
    scope_class_ids: set[int] | None
    reviewable_statuses: set[str]


class ReviewError(Exception):
    def __init__(self, message: str, code: int = 1000):
        self.message = message
        self.code = code
        super().__init__(message)


def _ensure_utc_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _resolve_review_actor(db: Session, user: User) -> ReviewActorContext:
    if user.role in {"teacher", "admin"}:
        return ReviewActorContext(
            scope_class_ids=None,
            reviewable_statuses=TEACHER_REVIEWABLE_STATUSES,
        )

    if user.role not in {"student", "reviewer"}:
        raise ReviewError("无权限", 1003)
    if not user.is_reviewer or user.reviewer_token_id is None:
        raise ReviewError("无权限", 1003)

    token = db.get(ReviewerToken, user.reviewer_token_id)
    if token is None:
        user.is_reviewer = False
        user.reviewer_token_id = None
        db.add(user)
        db.commit()
        raise ReviewError("无权限", 1003)

    now = datetime.now(timezone.utc)
    if token.is_revoked or _ensure_utc_aware(token.expired_at) < now:
        user.is_reviewer = False
        user.reviewer_token_id = None
        db.add(user)
        db.commit()
        raise ReviewError("无权限", 1003)

    scope_class_ids = set(token.class_ids)
    if not scope_class_ids:
        raise ReviewError("无权限", 1003)
    return ReviewActorContext(
        scope_class_ids=scope_class_ids,
        reviewable_statuses=REVIEWER_REVIEWABLE_STATUSES,
    )


def _scope_conditions(*, scope_class_ids: set[int] | None, class_id: int | None) -> tuple[list, int | None]:
    if class_id is not None and scope_class_ids is not None and class_id not in scope_class_ids:
        raise ReviewError("无权限", 1003)

    effective_class_id = class_id
    conditions = [Application.is_deleted.is_(False), User.class_id.is_not(None)]
    if effective_class_id is not None:
        conditions.append(User.class_id == effective_class_id)
    elif scope_class_ids is not None:
        conditions.append(User.class_id.in_(list(scope_class_ids)))
    return conditions, effective_class_id


def get_pending_list(
    db: Session,
    user: User,
    *,
    class_id: int | None,
    category: str | None,
    sub_type: str | None,
    keyword: str | None,
    page: int,
    size: int,
) -> dict:
    actor = _resolve_review_actor(db, user)
    conditions, _ = _scope_conditions(scope_class_ids=actor.scope_class_ids, class_id=class_id)
    conditions.append(Application.status.in_(actor.reviewable_statuses))

    if category:
        conditions.append(Application.category == category)
    if sub_type:
        conditions.append(Application.sub_type == sub_type)
    if keyword:
        like = f"%{keyword}%"
        conditions.append(or_(Application.title.ilike(like), User.name.ilike(like), User.account.ilike(like)))

    stmt = (
        select(Application, User)
        .join(User, User.id == Application.applicant_id)
        .where(and_(*conditions))
        .order_by(Application.created_at.desc())
    )
    rows = db.exec(stmt).all()

    total = len(rows)
    start = (page - 1) * size
    end = start + size
    paged_rows = rows[start:end]

    data = []
    for application, applicant in paged_rows:
        data.append(
            {
                "application_id": application.id,
                "student_id": applicant.id,
                "student_name": applicant.name,
                "class_id": applicant.class_id,
                "title": application.title,
                "category": application.category,
                "sub_type": application.sub_type,
                "status": application.status,
                "score": application.score,
                "created_at": application.created_at.isoformat(),
            }
        )

    return {
        "page": page,
        "size": size,
        "total": total,
        "list": data,
    }


def get_pending_category_summary(
    db: Session,
    user: User,
    *,
    class_id: int | None,
    term: str | None,
) -> dict:
    actor = _resolve_review_actor(db, user)
    conditions, effective_class_id = _scope_conditions(scope_class_ids=actor.scope_class_ids, class_id=class_id)
    conditions.append(Application.status.in_(actor.reviewable_statuses))

    stmt = (
        select(Application, User)
        .join(User, User.id == Application.applicant_id)
        .where(and_(*conditions))
        .order_by(Application.created_at.desc())
    )
    rows = db.exec(stmt).all()

    category_map: dict[str, dict] = {}

    for application, _ in rows:
        if application.category not in category_map:
            category_map[application.category] = {
                "category": application.category,
                "category_name": application.category,
                "pending_count": 0,
                "approved_count": 0,
                "rejected_count": 0,
            }
        item = category_map[application.category]

        if application.status in actor.reviewable_statuses:
            item["pending_count"] += 1
        elif application.status == "approved":
            item["approved_count"] += 1
        elif application.status == "rejected":
            item["rejected_count"] += 1

    return {
        "class_id": effective_class_id,
        "term": term,
        "categories": list(category_map.values()),
    }


def get_pending_by_category(
    db: Session,
    user: User,
    *,
    class_id: int | None,
    category: str,
    sub_type: str | None,
    term: str | None,
    page: int,
    size: int,
) -> dict:
    actor = _resolve_review_actor(db, user)
    conditions, effective_class_id = _scope_conditions(scope_class_ids=actor.scope_class_ids, class_id=class_id)
    conditions.extend([Application.category == category, Application.status.in_(actor.reviewable_statuses)])
    if sub_type:
        conditions.append(Application.sub_type == sub_type)

    stmt = (
        select(Application, User)
        .join(User, User.id == Application.applicant_id)
        .where(and_(*conditions))
        .order_by(Application.created_at.desc())
    )
    rows = db.exec(stmt).all()

    total = len(rows)
    start = (page - 1) * size
    end = start + size
    paged_rows = rows[start:end]

    data = []
    for application, applicant in paged_rows:
        data.append(
            {
                "application_id": application.id,
                "student_name": applicant.name,
                "status": application.status,
                "score": application.score,
            }
        )

    return {
        "class_id": effective_class_id,
        "category": category,
        "term": term,
        "page": page,
        "size": size,
        "total": total,
        "list": data,
    }


def get_review_detail(db: Session, user: User, *, application_id: int) -> dict:
    actor = _resolve_review_actor(db, user)
    row = db.exec(
        select(Application, User)
        .join(User, User.id == Application.applicant_id)
        .where(Application.id == application_id, Application.is_deleted.is_(False))
    ).first()

    if not row:
        raise ReviewError("资源不存在", 1002)

    application, applicant = row
    if actor.scope_class_ids is not None and applicant.class_id not in actor.scope_class_ids:
        raise ReviewError("无权限", 1003)
    if application.status not in actor.reviewable_statuses:
        raise ReviewError("无权限", 1003)

    return {
        "id": application.id,
        "student": {
            "id": applicant.id,
            "name": applicant.name,
            "account": applicant.account,
            "class_id": applicant.class_id,
        },
        "category": application.category,
        "sub_type": application.sub_type,
        "uid": application.award_uid,
        "award_uid": application.award_uid,
        "title": application.title,
        "description": application.description,
        "occurred_at": application.occurred_at.isoformat(),
        "attachments": application.attachments,
        "status": application.status,
        "score": application.score,
        "comment": application.comment,
        "created_at": application.created_at.isoformat(),
        "updated_at": application.updated_at.isoformat(),
    }


def submit_review_decision(
    db: Session,
    user: User,
    *,
    application_id: int,
    decision: str,
    comment: str | None,
    reason_code: str | None,
    reason_text: str | None,
) -> tuple[Application, ReviewRecord]:
    actor = _resolve_review_actor(db, user)

    normalized_decision = decision.strip().lower()
    if normalized_decision not in {"approved", "rejected"}:
        raise ReviewError("decision 参数不合法", 1001)

    if normalized_decision == "rejected" and (not reason_code or not reason_text):
        raise ReviewError("驳回时 reason_code/reason_text 必填", 1001)

    row = db.exec(
        select(Application, User)
        .join(User, User.id == Application.applicant_id)
        .where(Application.id == application_id, Application.is_deleted.is_(False))
    ).first()
    if not row:
        raise ReviewError("资源不存在", 1002)

    application, applicant = row
    if actor.scope_class_ids is not None and applicant.class_id not in actor.scope_class_ids:
        raise ReviewError("无权限", 1003)
    if application.status not in actor.reviewable_statuses:
        raise ReviewError("当前状态不允许审核", 1000)

    target_status = normalized_decision
    if actor.scope_class_ids is not None and normalized_decision == "approved":
        target_status = "pending_teacher"

    application.status = target_status
    application.comment = comment or reason_text
    application.version += 1
    application.updated_at = datetime.now(timezone.utc)

    review_record = ReviewRecord(
        application_id=application.id,
        reviewer_user_id=user.id,
        decision=normalized_decision,
        comment=comment,
        reason_code=reason_code,
        reason_text=reason_text,
    )

    db.add(application)
    db.add(review_record)
    db.commit()
    db.refresh(application)
    db.refresh(review_record)
    return application, review_record


def get_review_history(
    db: Session,
    user: User,
    *,
    result: str | None,
    from_at: datetime | None,
    to_at: datetime | None,
    page: int,
    size: int,
) -> dict:
    _ = _resolve_review_actor(db, user)

    conditions = [ReviewRecord.reviewer_user_id == user.id]
    if result:
        normalized_result = result.strip().lower()
        if normalized_result not in {"approved", "rejected"}:
            raise ReviewError("result 参数不合法", 1001)
        conditions.append(ReviewRecord.decision == normalized_result)
    if from_at:
        conditions.append(ReviewRecord.created_at >= _ensure_utc_aware(from_at))
    if to_at:
        conditions.append(ReviewRecord.created_at <= _ensure_utc_aware(to_at))

    stmt = (
        select(ReviewRecord, Application, User)
        .join(Application, Application.id == ReviewRecord.application_id)
        .join(User, User.id == Application.applicant_id)
        .where(and_(*conditions))
        .order_by(ReviewRecord.created_at.desc())
    )
    rows = db.exec(stmt).all()

    total = len(rows)
    start = (page - 1) * size
    end = start + size
    paged_rows = rows[start:end]

    data = []
    for record, application, applicant in paged_rows:
        data.append(
            {
                "application_id": application.id,
                "student_name": applicant.name,
                "class_id": applicant.class_id,
                "title": application.title,
                "result": record.decision,
                "comment": record.comment,
                "reason_code": record.reason_code,
                "reason_text": record.reason_text,
                "reviewed_at": record.created_at.isoformat(),
            }
        )

    return {
        "page": page,
        "size": size,
        "total": total,
        "list": data,
    }


def get_pending_count(db: Session, user: User) -> dict:
    actor = _resolve_review_actor(db, user)

    conditions = [
        Application.is_deleted.is_(False),
        Application.status.in_(actor.reviewable_statuses),
    ]
    if actor.scope_class_ids is not None:
        conditions.append(User.class_id.in_(list(actor.scope_class_ids)))

    stmt = (
        select(Application.id)
        .join(User, User.id == Application.applicant_id)
        .where(and_(*conditions))
    )
    count = len(db.exec(stmt).all())
    return {"pending_count": count}
