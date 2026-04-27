from pathlib import Path
from uuid import uuid4

from sqlmodel import Session, select

from app.core.cache import build_idempotency_key, get_json, set_json
from app.core.config import settings
from app.core.constants import MANAGE_REVIEW_ROLES
from app.core.utils import json_dumps, json_loads
from app.models.archive_record import ArchiveRecord
from app.models.export_task import ExportTask
from app.models.user import User
from app.schemas.archive import ArchiveExportCreateRequest
from app.services.errors import ServiceError
from app.services.serializers import serialize_archive, serialize_export_task
from app.services.system_log_service import write_system_log
from app.tasks.jobs import enqueue_export_job


def create_teacher_export_task(
    db: Session,
    user: User,
    payload: ArchiveExportCreateRequest,
    *,
    idempotency_key: str | None,
    store_to_archive: bool = False,
) -> dict:
    _require_teacher(user)
    cache_key = None
    if idempotency_key:
        cache_key = build_idempotency_key("teacher_export", idempotency_key)
        cached = get_json(cache_key)
        if cached:
            existing = db.exec(select(ExportTask).where(ExportTask.task_id == cached["task_id"])).first()
            if existing:
                return {"task_id": existing.task_id}

    task = ExportTask(
        task_id=f"exp_{uuid4().hex[:12]}",
        scope=payload.scope,
        format=payload.format,
        filters_json=json_dumps(payload.filters),
        options_json=json_dumps({"store_to_archive": store_to_archive}),
        created_by=user.id,
        status="queued",
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    if cache_key:
        set_json(cache_key, {"task_id": task.task_id}, ttl_seconds=3600)
    enqueue_export_job(task.task_id)
    write_system_log(db, action="export.create", actor_id=user.id, target_type="export_task", target_id=task.task_id)
    return {"task_id": task.task_id}


def get_export_task(db: Session, user: User, task_id: str) -> dict:
    _require_teacher(user)
    task = db.exec(select(ExportTask).where(ExportTask.task_id == task_id)).first()
    if not task:
        raise ServiceError("export task not found", 1002)
    return serialize_export_task(task)


def get_export_file_path(db: Session, user: User, task_id: str) -> Path:
    _require_teacher(user)
    task = db.exec(select(ExportTask).where(ExportTask.task_id == task_id)).first()
    if not task:
        raise ServiceError("export task not found", 1002)
    if task.status != "completed" or not task.file_path:
        raise ServiceError("export file is not ready", 1000)
    path = Path(task.file_path)
    if not path.exists():
        raise ServiceError("export file not found", 1002)
    return path


def list_archives(db: Session, user: User, *, term: str | None, grade: int | None, class_id: int | None) -> list[dict]:
    if user.role not in {"teacher", "admin"}:
        raise ServiceError("permission denied", 1003)
    stmt = select(ArchiveRecord)
    if term:
        stmt = stmt.where(ArchiveRecord.term == term)
    if grade:
        stmt = stmt.where(ArchiveRecord.grade == grade)
    rows = db.exec(stmt.order_by(ArchiveRecord.created_at.desc())).all()
    data = []
    for row in rows:
        class_ids = json_loads(row.class_ids_json, [])
        if class_id and class_id not in class_ids:
            continue
        data.append(serialize_archive(row))
    return data


def get_archive_detail(db: Session, user: User, archive_id: str) -> dict:
    if user.role not in {"teacher", "admin"}:
        raise ServiceError("permission denied", 1003)
    row = db.exec(select(ArchiveRecord).where(ArchiveRecord.archive_id == archive_id)).first()
    if not row:
        raise ServiceError("archive not found", 1002)
    return serialize_archive(row)


def get_archive_download_path(db: Session, user: User, archive_id: str) -> Path:
    row = db.exec(select(ArchiveRecord).where(ArchiveRecord.archive_id == archive_id)).first()
    if not row:
        raise ServiceError("archive not found", 1002)
    if user.role not in {"teacher", "admin"}:
        raise ServiceError("permission denied", 1003)
    task = db.exec(select(ExportTask).where(ExportTask.task_id == row.export_task_id)).first()
    if not task or task.status != "completed" or not task.file_path:
        raise ServiceError("archive file is not ready", 1000)
    path = Path(task.file_path)
    if not path.exists():
        raise ServiceError("archive file not found", 1002)
    return path


def create_archive_record_from_task(db: Session, task: ExportTask) -> ArchiveRecord:
    existing = db.exec(select(ArchiveRecord).where(ArchiveRecord.export_task_id == task.task_id)).first()
    if existing:
        return existing

    filters = json_loads(task.filters_json, {})
    archive = ArchiveRecord(
        archive_id=f"arc_{uuid4().hex[:12]}",
        archive_name=f"archive_{task.task_id}",
        term=filters.get("term") or settings.default_term,
        grade=filters.get("grade"),
        class_ids_json=json_dumps([filters["class_id"]]) if filters.get("class_id") else json_dumps([]),
        export_task_id=task.task_id,
    )
    db.add(archive)
    db.commit()
    db.refresh(archive)
    return archive


def _require_teacher(user: User) -> None:
    if user.role not in MANAGE_REVIEW_ROLES:
        raise ServiceError("permission denied", 1003)
