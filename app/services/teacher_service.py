from collections import defaultdict

from sqlalchemy import func, or_
from sqlmodel import Session, select

from app.core.constants import (
    CLASS_GRADE_MAP,
    MANAGE_REVIEW_ROLES,
    SCORE_INCLUDED_STATUSES,
    TEACHER_RECHECKABLE_STATUSES,
)
from app.core.utils import utcnow
from app.models.application import Application
from app.models.review_record import ReviewRecord
from app.models.user import User
from app.schemas.review import TeacherRecheckRequest
from app.services.errors import ServiceError
from app.services.notification_service import enqueue_reject_email_for_application
from app.services.score_summary_service import add_student_actual_score, get_student_actual_score_map
from app.services.system_log_service import write_system_log

PENDING_STATUSES = {"pending_ai", "pending_review", "ai_abnormal"}
ARCHIVABLE_STATUSES = {"approved", "rejected"}


def list_teacher_applications(
    db: Session,
    user: User,
    *,
    grade: int | None,
    class_id: int | None,
    status: str | None,
    category: str | None,
    sub_type: str | None,
    keyword: str | None,
    page: int,
    size: int,
) -> dict:
    _require_teacher(user)
    stmt = select(Application, User).join(User, Application.applicant_id == User.id).where(Application.is_deleted.is_(False))
    if class_id:
        stmt = stmt.where(User.class_id == class_id)
    if grade:
        class_ids = [cid for cid, grade_value in CLASS_GRADE_MAP.items() if grade_value == grade]
        if class_ids:
            stmt = stmt.where(User.class_id.in_(class_ids))
    if status:
        stmt = stmt.where(Application.status == status)
    if category:
        stmt = stmt.where(Application.category == category)
    if sub_type:
        stmt = stmt.where(Application.sub_type == sub_type)
    if keyword:
        like_value = f"%{keyword}%"
        stmt = stmt.where(or_(Application.title.ilike(like_value), User.name.ilike(like_value), User.account.ilike(like_value)))
    total = db.exec(select(func.count()).select_from(stmt.subquery())).one()
    rows = db.exec(stmt.order_by(Application.updated_at.desc()).offset((page - 1) * size).limit(size)).all()
    data = []
    for application, student in rows:
        data.append(
            {
                "application_id": application.id,
                "grade": CLASS_GRADE_MAP.get(student.class_id),
                "class_id": student.class_id,
                "student_id": student.id,
                "student_account": student.account,
                "student_name": student.name,
                "title": application.title,
                "category": application.category,
                "sub_type": application.sub_type,
                "project": f"{application.category} / {application.sub_type}",
                "description": application.description,
                "status": application.status,
                "score": application.item_score,
                "comment": application.comment,
                "created_at": application.created_at.isoformat(),
                "updated_at": application.updated_at.isoformat(),
            }
        )
    return {"page": page, "size": size, "total": total, "list": data}


def recheck_application(db: Session, user: User, application_id: int, payload: TeacherRecheckRequest) -> dict:
    _require_teacher(user)
    application = db.get(Application, application_id)
    if not application or application.is_deleted:
        raise ServiceError("application not found", 1002)
    if application.status not in TEACHER_RECHECKABLE_STATUSES:
        raise ServiceError("teacher cannot review this status", 1000)

    student = db.get(User, application.applicant_id)
    application.status = "approved" if payload.decision == "approved" else "rejected"
    application.comment = payload.comment
    if payload.score is not None:
        application.item_score = payload.score
        application.total_score = payload.score
    application.updated_at = utcnow()
    application.version += 1
    db.add(application)

    record = ReviewRecord(
        application_id=application.id,
        reviewer_id=user.id,
        reviewer_role="teacher",
        decision=payload.decision,
        result=application.status,
        comment=payload.comment,
    )
    db.add(record)
    db.commit()
    if application.status == "rejected" and student and student.email:
        enqueue_reject_email_for_application(db, actor=user, application=application, to_email=student.email)
    write_system_log(
        db,
        action="teacher.recheck",
        actor_id=user.id,
        target_type="application",
        target_id=str(application.id),
        detail={"decision": payload.decision, "score": payload.score},
    )
    return {
        "application_id": application.id,
        "status": application.status,
        "comment": application.comment,
        "updated_at": application.updated_at.isoformat(),
    }


def archive_applications(db: Session, user: User, application_ids: list[int]) -> dict:
    _require_teacher(user)
    unique_ids = list(dict.fromkeys(application_ids))
    archived = []
    skipped = []
    for application_id in unique_ids:
        application = db.get(Application, application_id)
        if not application or application.is_deleted:
            skipped.append({"application_id": application_id, "reason": "not_found"})
            continue
        if application.status == "archived":
            skipped.append({"application_id": application_id, "reason": "already_archived"})
            continue
        if application.status not in ARCHIVABLE_STATUSES:
            skipped.append({"application_id": application_id, "reason": "invalid_status"})
            continue

        # Scheme-2 actual score: only approved items contribute when first archived.
        if application.status == "approved" and not application.actual_score_recorded:
            add_student_actual_score(db, application.applicant_id, float(application.item_score or 0.0))
            application.actual_score_recorded = True

        application.status = "archived"
        application.updated_at = utcnow()
        application.version += 1
        db.add(application)
        archived.append(application_id)
    db.commit()
    write_system_log(
        db,
        action="teacher.archive",
        actor_id=user.id,
        target_type="application_batch",
        target_id=",".join(str(item) for item in archived),
        detail={"skipped": skipped},
    )
    return {
        "total": len(unique_ids),
        "success_count": len(archived),
        "skipped_count": len(skipped),
        "archived_application_ids": archived,
        "skipped": skipped,
    }


def get_statistics(db: Session, user: User, *, grade: int | None, class_id: int | None) -> dict:
    _require_teacher(user)
    rows = list_teacher_applications(
        db,
        user,
        grade=grade,
        class_id=class_id,
        status=None,
        category=None,
        sub_type=None,
        keyword=None,
        page=1,
        size=10000,
    )["list"]
    by_status = defaultdict(int)
    by_category = defaultdict(int)
    total_score = 0.0
    for row in rows:
        by_status[row["status"]] += 1
        by_category[row["category"]] += 1
        if row["status"] in SCORE_INCLUDED_STATUSES:
            total_score += float(row["score"] or 0.0)
    return {
        "total_count": len(rows),
        "status_summary": dict(by_status),
        "category_summary": dict(by_category),
        "total_score": round(total_score, 4),
        "average_score": round(total_score / len(rows), 4) if rows else 0.0,
    }


def get_class_statistics(db: Session, user: User, *, grade: int | None, class_id: int | None) -> dict:
    _require_teacher(user)
    rows = list_teacher_applications(
        db,
        user,
        grade=grade,
        class_id=class_id,
        status=None,
        category=None,
        sub_type=None,
        keyword=None,
        page=1,
        size=10000,
    )["list"]
    summary: dict[int, dict] = {}
    for row in rows:
        cid = row["class_id"]
        if cid not in summary:
            summary[cid] = {
                "grade": row["grade"],
                "class_id": cid,
                "total_count": 0,
                "rejected_count": 0,
                "pending_count": 0,
                "total_score": 0.0,
            }
        item = summary[cid]
        item["total_count"] += 1
        if row["status"] in SCORE_INCLUDED_STATUSES:
            item["total_score"] += float(row["score"] or 0.0)
        if row["status"] == "rejected":
            item["rejected_count"] += 1
        if row["status"] in PENDING_STATUSES:
            item["pending_count"] += 1

    result = []
    for item in summary.values():
        count = item["total_count"]
        result.append(
            {
                **item,
                "average_score": round(item["total_score"] / count, 4) if count else 0.0,
                "total_score": round(item["total_score"], 4),
            }
        )
    result.sort(key=lambda item: (item["grade"] or 0, item["class_id"] or 0))
    return {"list": result}


def get_student_statistics(db: Session, user: User, *, grade: int | None, class_id: int | None) -> dict:
    _require_teacher(user)
    rows = list_teacher_applications(
        db,
        user,
        grade=grade,
        class_id=class_id,
        status=None,
        category=None,
        sub_type=None,
        keyword=None,
        page=1,
        size=10000,
    )["list"]
    summary: dict[int, dict] = {}
    for row in rows:
        student_id = row["student_id"]
        if student_id not in summary:
            summary[student_id] = {
                "grade": row["grade"],
                "class_id": row["class_id"],
                "student_id": student_id,
                "student_account": row["student_account"],
                "student_name": row["student_name"],
                "total_count": 0,
                "rejected_count": 0,
                "pending_count": 0,
                "total_score": 0.0,
            }
        item = summary[student_id]
        item["total_count"] += 1
        if row["status"] in SCORE_INCLUDED_STATUSES:
            item["total_score"] += float(row["score"] or 0.0)
        if row["status"] == "rejected":
            item["rejected_count"] += 1
        if row["status"] in PENDING_STATUSES:
            item["pending_count"] += 1

    actual_score_map = get_student_actual_score_map(db, list(summary.keys()))

    result = []
    for item in summary.values():
        total_count = int(item["total_count"] or 0)
        result.append(
            {
                **item,
                "total_score": round(item["total_score"], 4),
                "average_score": round(item["total_score"] / total_count, 4) if total_count else 0.0,
                "actual_score": round(float(actual_score_map.get(item["student_id"], 0.0)), 4),
            }
        )
    result.sort(key=lambda item: (item["grade"] or 0, item["class_id"] or 0, item["student_account"] or ""))
    return {"list": result}


def _require_teacher(user: User) -> None:
    if user.role not in MANAGE_REVIEW_ROLES:
        raise ServiceError("permission denied", 1003)
