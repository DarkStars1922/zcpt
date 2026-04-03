from datetime import datetime, timezone

from sqlmodel import Session, select

from app.core.constants import ANNOUNCEMENT_STATUS_ACTIVE, ANNOUNCEMENT_STATUS_CLOSED, CLASS_GRADE_MAP
from app.core.utils import json_dumps, json_loads, utcnow
from app.models.announcement import Announcement
from app.models.archive_record import ArchiveRecord
from app.models.user import User
from app.schemas.announcement import AnnouncementCreateRequest, AnnouncementUpdateRequest
from app.services.errors import ServiceError
from app.services.serializers import serialize_announcement
from app.services.system_log_service import write_system_log


def create_announcement(db: Session, user: User, payload: AnnouncementCreateRequest) -> dict:
    _require_manage(user)
    archive = _get_archive(db, payload.archive_id)
    announcement = Announcement(
        archive_record_id=archive.id,
        title=payload.title,
        scope_json=json_dumps(payload.scope.model_dump()),
        show_fields_json=json_dumps(payload.show_fields),
        start_at=payload.start_at,
        end_at=payload.end_at,
        created_by=user.id,
        updated_at=utcnow(),
    )
    db.add(announcement)
    archive.is_announced = True
    db.add(archive)
    db.commit()
    db.refresh(announcement)
    write_system_log(
        db,
        action="announcement.create",
        actor_id=user.id,
        target_type="announcement",
        target_id=str(announcement.id),
    )
    return serialize_announcement(announcement, archive.archive_id)


def list_announcements(db: Session, user: User) -> list[dict]:
    rows = db.exec(
        select(Announcement, ArchiveRecord)
        .join(ArchiveRecord, Announcement.archive_record_id == ArchiveRecord.id)
        .order_by(Announcement.created_at.desc())
    ).all()
    if user.role == "student":
        rows = [(announcement, archive) for announcement, archive in rows if can_student_view_announcement(announcement, user)]
    return [serialize_announcement(announcement, archive.archive_id) for announcement, archive in rows]


def update_announcement(db: Session, user: User, announcement_id: int, payload: AnnouncementUpdateRequest) -> dict:
    _require_manage(user)
    announcement = db.get(Announcement, announcement_id)
    if not announcement:
        raise ServiceError("announcement not found", 1002)
    archive = _get_archive(db, payload.archive_id)
    announcement.archive_record_id = archive.id
    announcement.title = payload.title
    announcement.scope_json = json_dumps(payload.scope.model_dump())
    announcement.show_fields_json = json_dumps(payload.show_fields)
    announcement.start_at = payload.start_at
    announcement.end_at = payload.end_at
    announcement.updated_at = utcnow()
    db.add(announcement)
    db.commit()
    db.refresh(announcement)
    write_system_log(
        db,
        action="announcement.update",
        actor_id=user.id,
        target_type="announcement",
        target_id=str(announcement.id),
    )
    return serialize_announcement(announcement, archive.archive_id)


def close_announcement(db: Session, user: User, announcement_id: int) -> dict:
    _require_manage(user)
    announcement = db.get(Announcement, announcement_id)
    if not announcement:
        raise ServiceError("announcement not found", 1002)
    announcement.status = ANNOUNCEMENT_STATUS_CLOSED
    announcement.closed_at = utcnow()
    announcement.updated_at = utcnow()
    db.add(announcement)
    db.commit()
    archive = db.get(ArchiveRecord, announcement.archive_record_id)
    return serialize_announcement(announcement, archive.archive_id if archive else "")


def delete_announcement(db: Session, user: User, announcement_id: int) -> None:
    _require_manage(user)
    announcement = db.get(Announcement, announcement_id)
    if not announcement:
        raise ServiceError("announcement not found", 1002)
    db.delete(announcement)
    db.commit()
    write_system_log(
        db,
        action="announcement.delete",
        actor_id=user.id,
        target_type="announcement",
        target_id=str(announcement_id),
    )


def can_student_view_announcement(announcement: Announcement, user: User) -> bool:
    if user.role != "student":
        return False
    if announcement.status != ANNOUNCEMENT_STATUS_ACTIVE:
        return False

    now = _normalize_datetime(utcnow())
    start_at = _normalize_datetime(announcement.start_at)
    end_at = _normalize_datetime(announcement.end_at)

    if start_at > now:
        return False
    if end_at and end_at < now:
        return False

    scope = json_loads(announcement.scope_json, {})
    scope_grade = scope.get("grade")
    scope_class_ids = [int(item) for item in (scope.get("class_ids") or [])]
    user_grade = CLASS_GRADE_MAP.get(user.class_id) if user.class_id is not None else None

    if scope_grade is not None and user_grade != int(scope_grade):
        return False
    if scope_class_ids and user.class_id not in scope_class_ids:
        return False
    return True


def _require_manage(user: User) -> None:
    if user.role not in {"teacher", "admin"}:
        raise ServiceError("permission denied", 1003)


def _get_archive(db: Session, archive_id: str) -> ArchiveRecord:
    archive = db.exec(select(ArchiveRecord).where(ArchiveRecord.archive_id == archive_id)).first()
    if not archive:
        raise ServiceError("archive not found", 1002)
    return archive


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
