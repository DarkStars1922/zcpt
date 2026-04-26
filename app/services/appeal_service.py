from sqlalchemy import and_, func, or_
from sqlmodel import Session, select

from app.core.utils import utcnow
from app.models.announcement import Announcement
from app.models.application import Application
from app.models.appeal import Appeal
from app.models.appeal_attachment import AppealAttachment
from app.models.file_info import FileInfo
from app.models.user import User
from app.schemas.appeal import AppealCreateRequest, AppealProcessRequest
from app.services.announcement_service import can_student_view_announcement, _query_public_applications, _query_public_students
from app.services.errors import ServiceError
from app.services.score_summary_service import recalculate_student_score
from app.services.serializers import serialize_appeal, serialize_file
from app.services.system_log_service import write_system_log


def create_appeal(db: Session, user: User, payload: AppealCreateRequest) -> dict:
    if user.role != "student":
        raise ServiceError("permission denied", 1003)
    announcement = db.get(Announcement, payload.announcement_id)
    if not announcement:
        raise ServiceError("announcement not found", 1002)
    if not can_student_view_announcement(announcement, user, db=db):
        raise ServiceError("permission denied", 1003)

    if payload.application_id:
        application = db.get(Application, payload.application_id)
        if not application or application.is_deleted:
            raise ServiceError("application not found", 1002)
        public_application_ids = {row.id for row, _ in _query_public_applications(db, announcement)}
        if application.id not in public_application_ids:
            raise ServiceError("该申报不在当前公示范围内", 1003)
    appeal = Appeal(
        announcement_id=payload.announcement_id,
        student_id=user.id,
        application_id=payload.application_id,
        is_anonymous=payload.is_anonymous,
        content=payload.content,
    )
    db.add(appeal)
    db.flush()
    _replace_attachments(db, user, appeal.id, [item.file_id for item in payload.attachments], auto_commit=False)
    db.commit()
    db.refresh(appeal)
    write_system_log(
        db,
        action="appeal.create",
        actor_id=user.id,
        target_type="appeal",
        target_id=str(appeal.id),
    )
    return {
        "id": appeal.id,
        "announcement_id": appeal.announcement_id,
        "application_id": appeal.application_id,
        "is_anonymous": bool(appeal.is_anonymous),
        "status": appeal.status,
        "created_at": appeal.created_at.isoformat(),
    }


def list_appeals(
    db: Session,
    user: User,
    *,
    page: int,
    size: int,
    student_id: int | None,
    status: str | None,
    announcement_id: int | None,
    student_name: str | None = None,
    keyword: str | None = None,
) -> dict:
    stmt = select(Appeal)
    needs_student_join = bool(student_name or keyword)
    if needs_student_join:
        stmt = stmt.join(User, Appeal.student_id == User.id)
    if user.role == "student":
        stmt = stmt.where(Appeal.student_id == user.id)
    elif user.role not in {"teacher", "admin"}:
        raise ServiceError("permission denied", 1003)
    if student_id:
        stmt = stmt.where(Appeal.student_id == student_id)
    if status:
        stmt = stmt.where(Appeal.status == status)
    if announcement_id:
        stmt = stmt.where(Appeal.announcement_id == announcement_id)
    if student_name:
        like = f"%{student_name.strip()}%"
        if user.role in {"teacher", "admin"}:
            stmt = stmt.where(Appeal.is_anonymous.is_(False))
        stmt = stmt.where(or_(User.name.like(like), User.account.like(like)))
    if keyword:
        like = f"%{keyword.strip()}%"
        if needs_student_join:
            if user.role in {"teacher", "admin"}:
                stmt = stmt.where(
                    or_(
                        Appeal.content.like(like),
                        and_(Appeal.is_anonymous.is_(False), or_(User.name.like(like), User.account.like(like))),
                    )
                )
            else:
                stmt = stmt.where(or_(Appeal.content.like(like), User.name.like(like), User.account.like(like)))
        else:
            stmt = stmt.where(Appeal.content.like(like))
    total = db.exec(select(func.count()).select_from(stmt.subquery())).one()
    rows = db.exec(stmt.order_by(Appeal.created_at.desc()).offset((page - 1) * size).limit(size)).all()
    result = []
    for row in rows:
        student = db.get(User, row.student_id)
        result.append(serialize_appeal(row, student=student, attachments=_get_attachments(db, row.id), viewer=user))
    return {"page": page, "size": size, "total": total, "list": result}


def search_appeal_target_applications(
    db: Session,
    user: User,
    *,
    student_name: str | None = None,
    student_id: int | None = None,
    announcement_id: int | None = None,
    appeal_id: int | None = None,
    keyword: str | None = None,
    limit: int = 20,
) -> list[dict]:
    if user.role not in {"teacher", "admin", "student"}:
        raise ServiceError("permission denied", 1003)

    appeal = db.get(Appeal, appeal_id) if appeal_id else None
    if appeal_id and not appeal:
        raise ServiceError("appeal not found", 1002)
    if appeal and user.role not in {"teacher", "admin"} and appeal.student_id != user.id:
        raise ServiceError("permission denied", 1003)

    if appeal:
        announcement_id = appeal.announcement_id
    if user.role == "student" and not announcement_id:
        raise ServiceError("announcement_id is required", 1001)

    stmt = (
        select(Application, User)
        .join(User, Application.applicant_id == User.id)
        .where(
            Application.is_deleted.is_(False),
            Application.status.in_(("approved", "archived")),
            User.role == "student",
            User.is_deleted.is_(False),
        )
    )
    if user.role in {"teacher", "admin"} and student_id:
        stmt = stmt.where(User.id == student_id)
    if student_name:
        like = f"%{student_name.strip()}%"
        stmt = stmt.where(or_(User.name.like(like), User.account.like(like)))
    if keyword:
        like = f"%{keyword.strip()}%"
        stmt = stmt.where(or_(Application.title.like(like), User.name.like(like), User.account.like(like)))
    if announcement_id:
        announcement = db.get(Announcement, announcement_id)
        if announcement:
            if user.role == "student" and not can_student_view_announcement(announcement, user, db=db):
                raise ServiceError("permission denied", 1003)
            allowed_student_ids = {row.id for row in _query_public_students(db, announcement) if row.id is not None}
            if not allowed_student_ids:
                return []
            stmt = stmt.where(Application.applicant_id.in_(allowed_student_ids))
            public_application_ids = {application.id for application, _ in _query_public_applications(db, announcement)}
            if public_application_ids:
                stmt = stmt.where(Application.id.in_(public_application_ids))
            else:
                return []

    rows = db.exec(
        stmt.order_by(User.class_id.asc(), User.account.asc(), Application.occurred_at.desc(), Application.id.desc())
        .limit(max(1, min(limit, 100)))
    ).all()
    return [
        {
            "application_id": application.id,
            "student_id": student.id,
            "student_name": student.name,
            "student_account": student.account,
            "class_id": student.class_id,
            "title": application.title,
            "status": application.status,
            "score": application.item_score,
            "occurred_at": application.occurred_at.isoformat() if application.occurred_at else None,
        }
        for application, student in rows
    ]


def process_appeal(db: Session, user: User, appeal_id: int, payload: AppealProcessRequest) -> dict:
    if user.role not in {"teacher", "admin"}:
        raise ServiceError("permission denied", 1003)
    appeal = db.get(Appeal, appeal_id)
    if not appeal:
        raise ServiceError("appeal not found", 1002)
    if appeal.status == "processed":
        raise ServiceError("appeal already processed", 1000)
    appeal.result = payload.result
    appeal.result_comment = payload.result_comment
    appeal.application_id = payload.application_id or appeal.application_id
    appeal.score_action = payload.score_action
    appeal.adjusted_score = payload.score
    appeal.status = "processed"
    appeal.processed_by = user.id
    appeal.processed_at = utcnow()
    db.add(appeal)
    changed_application = _apply_approved_appeal_score_action(db, appeal, payload) if payload.result == "approved" else None
    db.commit()
    write_system_log(
        db,
        action="appeal.process",
        actor_id=user.id,
        target_type="appeal",
        target_id=str(appeal.id),
        detail={
            "result": payload.result,
            "application_id": appeal.application_id,
            "score_action": appeal.score_action,
            "adjusted_score": appeal.adjusted_score,
        },
    )
    return {
        "id": appeal.id,
        "result": appeal.result,
        "result_comment": appeal.result_comment,
        "status": appeal.status,
        "application_id": appeal.application_id,
        "score_action": appeal.score_action,
        "adjusted_score": appeal.adjusted_score,
        "changed_application_id": changed_application.id if changed_application else None,
        "processed_at": appeal.processed_at.isoformat() if appeal.processed_at else None,
    }


def _apply_approved_appeal_score_action(
    db: Session,
    appeal: Appeal,
    payload: AppealProcessRequest,
) -> Application | None:
    if payload.score_action == "none":
        return None
    application_id = payload.application_id or appeal.application_id
    if not application_id:
        raise ServiceError("application_id is required for score appeal action", 1001)
    application = db.get(Application, application_id)
    if not application or application.is_deleted:
        raise ServiceError("application not found", 1002)
    announcement = db.get(Announcement, appeal.announcement_id)
    if not announcement:
        raise ServiceError("announcement not found", 1002)
    public_application_ids = {row.id for row, _ in _query_public_applications(db, announcement)}
    if application.id not in public_application_ids:
        raise ServiceError("该申报不在当前公示范围内", 1003)
    if application.status not in {"approved", "archived"}:
        raise ServiceError("application status cannot be changed by appeal", 1000)

    if payload.score_action == "cancel_application":
        if application.status == "approved":
            application.status = "rejected"
        application.actual_score_recorded = False
        application.comment = payload.result_comment or application.comment
    elif payload.score_action == "adjust_score":
        if payload.score is None:
            raise ServiceError("score is required for adjust_score", 1001)
        application.item_score = payload.score
        application.total_score = payload.score
        if application.status == "rejected":
            application.status = "approved"
        application.actual_score_recorded = application.status in {"approved", "archived"}
        application.comment = payload.result_comment or application.comment
    else:
        raise ServiceError("invalid score_action", 1001)

    application.updated_at = utcnow()
    application.version += 1
    db.add(application)
    db.flush()
    recalculate_student_score(db, application.applicant_id)
    return application


def _replace_attachments(
    db: Session,
    user: User,
    appeal_id: int,
    file_ids: list[str],
    *,
    auto_commit: bool = True,
) -> None:
    old_rows = db.exec(select(AppealAttachment).where(AppealAttachment.appeal_id == appeal_id)).all()
    for row in old_rows:
        db.delete(row)
    for file_id in dict.fromkeys(file_ids):
        file = db.get(FileInfo, file_id)
        if not file or file.status == "deleted":
            raise ServiceError(f"attachment not found: {file_id}", 1002)
        if file.uploader_id != user.id:
            raise ServiceError("attachment owner mismatch", 1003)
        db.add(AppealAttachment(appeal_id=appeal_id, file_id=file_id))
    if auto_commit:
        db.commit()


def _get_attachments(db: Session, appeal_id: int) -> list[dict]:
    rows = db.exec(
        select(AppealAttachment, FileInfo)
        .join(FileInfo, AppealAttachment.file_id == FileInfo.id)
        .where(AppealAttachment.appeal_id == appeal_id, FileInfo.status != "deleted")
    ).all()
    return [serialize_file(file) for _, file in rows]
