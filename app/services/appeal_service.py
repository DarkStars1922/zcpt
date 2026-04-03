from sqlalchemy import func
from sqlmodel import Session, select

from app.core.utils import utcnow
from app.models.announcement import Announcement
from app.models.appeal import Appeal
from app.models.appeal_attachment import AppealAttachment
from app.models.file_info import FileInfo
from app.models.user import User
from app.schemas.appeal import AppealCreateRequest, AppealProcessRequest
from app.services.announcement_service import can_student_view_announcement
from app.services.errors import ServiceError
from app.services.serializers import serialize_appeal, serialize_file
from app.services.system_log_service import write_system_log


def create_appeal(db: Session, user: User, payload: AppealCreateRequest) -> dict:
    if user.role != "student":
        raise ServiceError("permission denied", 1003)
    announcement = db.get(Announcement, payload.announcement_id)
    if not announcement:
        raise ServiceError("announcement not found", 1002)
    if not can_student_view_announcement(announcement, user):
        raise ServiceError("permission denied", 1003)

    appeal = Appeal(announcement_id=payload.announcement_id, student_id=user.id, content=payload.content)
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
) -> dict:
    stmt = select(Appeal)
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
    total = db.exec(select(func.count()).select_from(stmt.subquery())).one()
    rows = db.exec(stmt.order_by(Appeal.created_at.desc()).offset((page - 1) * size).limit(size)).all()
    result = []
    for row in rows:
        student = db.get(User, row.student_id)
        result.append(serialize_appeal(row, student=student, attachments=_get_attachments(db, row.id)))
    return {"page": page, "size": size, "total": total, "list": result}


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
    appeal.status = "processed"
    appeal.processed_by = user.id
    appeal.processed_at = utcnow()
    db.add(appeal)
    db.commit()
    write_system_log(
        db,
        action="appeal.process",
        actor_id=user.id,
        target_type="appeal",
        target_id=str(appeal.id),
        detail={"result": payload.result},
    )
    return {
        "id": appeal.id,
        "result": appeal.result,
        "result_comment": appeal.result_comment,
        "status": appeal.status,
        "processed_at": appeal.processed_at.isoformat() if appeal.processed_at else None,
    }


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
