from hashlib import md5
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from sqlmodel import Session, select

from app.core.config import settings
from app.core.constants import REVIEWER_REVIEWABLE_STATUSES
from app.core.utils import json_loads
from app.models.application import Application
from app.models.application_attachment import ApplicationAttachment
from app.models.file_info import FileInfo
from app.services.file_analysis_service import analyze_file, get_file_analysis_record
from app.models.reviewer_token import ReviewerToken
from app.models.user import User
from app.services.errors import ServiceError
from app.services.serializers import serialize_file

CONTENT_TYPE_EXT_MAP = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


def ensure_storage_dirs() -> None:
    settings.upload_dir_path.mkdir(parents=True, exist_ok=True)
    settings.export_dir_path.mkdir(parents=True, exist_ok=True)


async def save_upload_file(db: Session, user: User, file: UploadFile) -> dict:
    ensure_storage_dirs()
    _validate_content_type(file)

    ext = _detect_extension(file)
    file_id = f"file_{uuid4().hex}{ext}"
    file_path = settings.upload_dir_path / file_id
    max_file_size = settings.upload_max_file_size

    file_size = 0
    digest = md5()
    with file_path.open("wb") as output:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            file_size += len(chunk)
            if file_size > max_file_size:
                output.close()
                file_path.unlink(missing_ok=True)
                raise ServiceError("file too large", 1008)
            output.write(chunk)
            digest.update(chunk)

    record = FileInfo(
        id=file_id,
        uploader_id=user.id,
        original_name=file.filename or file_id,
        storage_path=str(file_path),
        content_type=(file.content_type or "").lower() or None,
        size=file_size,
        md5=digest.hexdigest(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    analysis = analyze_file(db, record, uploader=user)
    return serialize_file(record, analysis=analysis)


def get_file_record(db: Session, file_id: str) -> FileInfo:
    record = db.get(FileInfo, file_id)
    if not record or record.status == "deleted":
        raise ServiceError("file not found", 1002)
    return record


def get_file_metadata(db: Session, user: User, file_id: str) -> dict:
    record = get_file_for_user(db, user, file_id)
    analysis = get_file_analysis_record(db, record.id)
    return serialize_file(record, analysis=analysis)


def get_file_path_for_user(db: Session, user: User, file_id: str) -> Path:
    record = get_file_for_user(db, user, file_id)
    path = Path(record.storage_path)
    if not path.exists() or not path.is_file():
        raise ServiceError("file not found", 1002)
    return path


def delete_file(db: Session, user: User, file_id: str) -> None:
    record = get_file_record(db, file_id)
    if user.role not in {"teacher", "admin"} and record.uploader_id != user.id:
        raise ServiceError("permission denied", 1003)
    record.status = "deleted"
    db.add(record)
    db.commit()


def _detect_extension(file: UploadFile) -> str:
    content_type = (file.content_type or "").lower()
    ext = CONTENT_TYPE_EXT_MAP.get(content_type)
    if ext:
        return ext
    suffix = Path(file.filename or "").suffix.lower()
    if suffix in {".pdf", ".jpg", ".jpeg", ".png", ".webp"}:
        return ".jpg" if suffix == ".jpeg" else suffix
    raise ServiceError("unsupported file type", 1008)


def _validate_content_type(file: UploadFile) -> None:
    content_type = (file.content_type or "").lower()
    suffix = Path(file.filename or "").suffix.lower()
    if content_type in settings.allowed_upload_content_types:
        return
    if suffix in {".pdf", ".jpg", ".jpeg", ".png", ".webp"}:
        return
    raise ServiceError("unsupported file type", 1008)


def get_file_for_user(db: Session, user: User, file_id: str) -> FileInfo:
    record = get_file_record(db, file_id)
    if user.role in {"teacher", "admin"}:
        return record
    if record.uploader_id == user.id:
        return record

    app_link = db.exec(
        select(ApplicationAttachment, Application)
        .join(Application, ApplicationAttachment.application_id == Application.id)
        .where(ApplicationAttachment.file_id == file_id)
    ).first()
    if app_link:
        _, application = app_link
        if application.applicant_id == user.id:
            return record
        if _can_reviewer_access_application_file(db, user, application):
            return record

    raise ServiceError("permission denied", 1003)


def _can_reviewer_access_application_file(db: Session, user: User, application: Application) -> bool:
    if user.role != "student" or not user.is_reviewer:
        return False
    if application.status not in REVIEWER_REVIEWABLE_STATUSES:
        return False
    applicant = db.get(User, application.applicant_id)
    if not applicant:
        return False
    return applicant.class_id in _get_active_reviewer_class_ids(db, user)


def _get_active_reviewer_class_ids(db: Session, user: User) -> list[int]:
    if not user.reviewer_token_id:
        return []
    token = db.get(ReviewerToken, user.reviewer_token_id)
    if not token or token.status != "active":
        return []
    return [int(item) for item in json_loads(token.class_ids_json, [])]
