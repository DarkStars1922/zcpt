from datetime import datetime

from sqlalchemy import func, or_
from sqlmodel import Session, select

from app.core.constants import (
    MANAGE_REVIEW_ROLES,
    REVIEWER_REVIEWABLE_STATUSES,
    ROLE_STUDENT,
    TEACHER_RECHECKABLE_STATUSES,
)
from app.core.utils import json_loads, utcnow
from app.models.application import Application
from app.models.review_record import ReviewRecord
from app.models.reviewer_token import ReviewerToken
from app.models.user import User
from app.schemas.review import BatchReviewDecisionRequest, ReviewDecisionRequest
from app.services.application_service import get_application_attachments
from app.services.errors import ServiceError
from app.services.notification_service import enqueue_reject_email_for_application
from app.services.serializers import serialize_application, serialize_review_record
from app.services.system_log_service import write_system_log


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
    applications, total = _query_pending_applications(
        db,
        user,
        class_id=class_id,
        category=category,
        sub_type=sub_type,
        keyword=keyword,
        page=page,
        size=size,
    )
    return {
        "page": page,
        "size": size,
        "total": total,
        "list": [_serialize_pending_row(row) for row in applications],
    }


def get_pending_category_summary(db: Session, user: User, *, class_id: int | None, term: str | None) -> dict:
    applications, _ = _query_pending_applications(
        db,
        user,
        class_id=class_id,
        category=None,
        sub_type=None,
        keyword=None,
        page=1,
        size=1000,
    )
    categories: dict[str, dict] = {}
    for application, _student in applications:
        item = categories.setdefault(
            application.category,
            {
                "category": application.category,
                "category_name": application.category,
                "pending_count": 0,
                "approved_count": 0,
                "rejected_count": 0,
            },
        )
        item["pending_count"] += 1
    return {
        "class_id": class_id,
        "term": term,
        "categories": list(categories.values()),
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
    applications, total = _query_pending_applications(
        db,
        user,
        class_id=class_id,
        category=category,
        sub_type=sub_type,
        keyword=None,
        page=page,
        size=size,
    )
    return {
        "class_id": class_id,
        "category": category,
        "term": term,
        "page": page,
        "size": size,
        "total": total,
        "list": [_serialize_pending_row(row) for row in applications],
    }


def get_pending_count(db: Session, user: User, *, class_id: int | None) -> dict:
    _, total = _query_pending_applications(
        db,
        user,
        class_id=class_id,
        category=None,
        sub_type=None,
        keyword=None,
        page=1,
        size=1,
    )
    return {"pending_count": total}


def get_review_detail(db: Session, user: User, application_id: int) -> dict:
    application, student = _get_reviewable_application(db, user, application_id)
    payload = serialize_application(
        application,
        attachments=get_application_attachments(db, application.id),
        include_detail=True,
    )
    payload["student"] = {
        "id": student.id,
        "name": student.name,
        "account": student.account,
        "class_id": student.class_id,
        "email": student.email,
    }
    return payload


def submit_review_decision(db: Session, user: User, application_id: int, payload: ReviewDecisionRequest) -> dict:
    application, student = _get_reviewable_application(db, user, application_id)
    new_status = _resolve_decision_status(user, application.status, payload.decision)
    application.status = new_status
    application.comment = payload.comment
    application.updated_at = utcnow()
    application.version += 1
    db.add(application)
    record = ReviewRecord(
        application_id=application.id,
        reviewer_id=user.id,
        reviewer_role=_resolve_reviewer_role(user),
        decision=payload.decision,
        result=new_status,
        comment=payload.comment,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    if new_status == "rejected" and student.email:
        enqueue_reject_email_for_application(db, actor=user, application=application, to_email=student.email)
    write_system_log(
        db,
        action="review.submit",
        actor_id=user.id,
        target_type="application",
        target_id=str(application.id),
        detail={"decision": payload.decision, "result": new_status},
    )
    return {
        "application_id": application.id,
        "status": application.status,
        "review_id": record.id,
        "reviewed_at": record.created_at.isoformat(),
    }


def submit_batch_review_decision(db: Session, user: User, payload: BatchReviewDecisionRequest) -> dict:
    result_list: list[dict] = []
    for application_id in payload.application_ids:
        result_list.append(
            submit_review_decision(
                db,
                user,
                application_id,
                ReviewDecisionRequest(decision=payload.decision, comment=payload.comment),
            )
        )
    return {
        "total": len(payload.application_ids),
        "success_count": len(result_list),
        "list": result_list,
    }


def get_review_history(
    db: Session,
    user: User,
    *,
    class_id: int | None,
    result: str | None,
    from_at: str | None,
    to_at: str | None,
    page: int,
    size: int,
) -> dict:
    _resolve_reviewer_role(user)
    stmt = select(ReviewRecord, Application, User).join(Application, ReviewRecord.application_id == Application.id).join(
        User, Application.applicant_id == User.id
    )
    stmt = stmt.where(ReviewRecord.reviewer_id == user.id)
    if class_id:
        stmt = stmt.where(User.class_id == class_id)
    if result:
        stmt = stmt.where(ReviewRecord.result == result)
    parsed_from = _parse_datetime(from_at)
    if parsed_from:
        stmt = stmt.where(ReviewRecord.created_at >= parsed_from)
    parsed_to = _parse_datetime(to_at)
    if parsed_to:
        stmt = stmt.where(ReviewRecord.created_at <= parsed_to)
    total = db.exec(select(func.count()).select_from(stmt.subquery())).one()
    rows = db.exec(stmt.order_by(ReviewRecord.created_at.desc()).offset((page - 1) * size).limit(size)).all()
    data = []
    for record, application, student in rows:
        item = serialize_review_record(record)
        item.update(
            {
                "student_name": student.name,
                "class_id": student.class_id,
                "title": application.title,
            }
        )
        data.append(item)
    return {"page": page, "size": size, "total": total, "list": data}


def _query_pending_applications(
    db: Session,
    user: User,
    *,
    class_id: int | None,
    category: str | None,
    sub_type: str | None,
    keyword: str | None,
    page: int,
    size: int,
) -> tuple[list[tuple[Application, User]], int]:
    role = _resolve_reviewer_role(user)
    stmt = select(Application, User).join(User, Application.applicant_id == User.id).where(Application.is_deleted.is_(False))
    if role == "teacher":
        stmt = stmt.where(Application.status == "pending_teacher")
    else:
        class_ids = _get_reviewer_class_ids(db, user)
        if not class_ids:
            return [], 0
        stmt = stmt.where(Application.status.in_(tuple(REVIEWER_REVIEWABLE_STATUSES)))
        stmt = stmt.where(User.class_id.in_(class_ids))
        stmt = stmt.where(Application.applicant_id != user.id)
    if class_id:
        stmt = stmt.where(User.class_id == class_id)
    if category:
        stmt = stmt.where(Application.category == category)
    if sub_type:
        stmt = stmt.where(Application.sub_type == sub_type)
    if keyword:
        like_value = f"%{keyword}%"
        stmt = stmt.where(or_(Application.title.ilike(like_value), User.name.ilike(like_value), User.account.ilike(like_value)))
    total = db.exec(select(func.count()).select_from(stmt.subquery())).one()
    rows = db.exec(stmt.order_by(Application.created_at.desc()).offset((page - 1) * size).limit(size)).all()
    return rows, total


def _get_reviewable_application(db: Session, user: User, application_id: int) -> tuple[Application, User]:
    row = db.exec(
        select(Application, User)
        .join(User, Application.applicant_id == User.id)
        .where(Application.id == application_id, Application.is_deleted.is_(False))
    ).first()
    if not row:
        raise ServiceError("resource not found", 1002)
    application, student = row
    role = _resolve_reviewer_role(user)
    if role == "teacher":
        if application.status not in TEACHER_RECHECKABLE_STATUSES:
            raise ServiceError("teacher cannot review this status", 1000)
    else:
        class_ids = _get_reviewer_class_ids(db, user)
        if student.class_id not in class_ids:
            raise ServiceError("permission denied", 1003)
        if application.applicant_id == user.id:
            raise ServiceError("permission denied", 1003)
        if application.status not in REVIEWER_REVIEWABLE_STATUSES:
            raise ServiceError("reviewer cannot review this status", 1000)
    return application, student


def _resolve_decision_status(user: User, current_status: str, decision: str) -> str:
    role = _resolve_reviewer_role(user)
    if role == "teacher":
        if current_status not in TEACHER_RECHECKABLE_STATUSES:
            raise ServiceError("teacher cannot review this status", 1000)
        return "approved" if decision == "approved" else "rejected"
    if current_status not in REVIEWER_REVIEWABLE_STATUSES:
        raise ServiceError("reviewer cannot review this status", 1000)
    return "pending_teacher" if decision == "approved" else "rejected"


def _resolve_reviewer_role(user: User) -> str:
    if user.role in MANAGE_REVIEW_ROLES:
        return "teacher"
    if user.role == ROLE_STUDENT and user.is_reviewer:
        return "reviewer"
    raise ServiceError("permission denied", 1003)


def _get_reviewer_class_ids(db: Session, user: User) -> list[int]:
    if not user.reviewer_token_id:
        return []
    token = db.get(ReviewerToken, user.reviewer_token_id)
    if not token or token.status != "active":
        return []
    return [int(item) for item in json_loads(token.class_ids_json, [])]


def _serialize_pending_row(row: tuple[Application, User]) -> dict:
    application, student = row
    payload = serialize_application(application)
    payload.update(
        {
            "student_id": student.id,
            "student_name": student.name,
            "student_account": student.account,
            "class_id": student.class_id,
        }
    )
    return payload


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
