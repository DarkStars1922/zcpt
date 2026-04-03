from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import FileResponse
from sqlmodel import Session

from app.core.database import get_db
from app.core.responses import error_response, success_response
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.archive import ArchiveExportCreateRequest
from app.services.archive_service import (
    create_teacher_export_task,
    get_archive_detail,
    get_archive_download_path,
    list_archives,
)
from app.services.errors import ServiceError

router = APIRouter(prefix="/archives", tags=["archives"])


@router.post("/exports")
def create_archive_export_api(
    request: Request,
    payload: ArchiveExportCreateRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        data = create_teacher_export_task(
            db,
            user,
            payload,
            idempotency_key=idempotency_key,
            store_to_archive=payload.store_to_archive,
        )
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="export task created", data=data)


@router.get("/exports")
def list_archives_api(
    request: Request,
    term: str | None = Query(default=None),
    grade: int | None = Query(default=None),
    class_id: int | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        data = list_archives(db, user, term=term, grade=grade, class_id=class_id)
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="fetch success", data=data)


@router.get("/exports/{archive_id}")
def get_archive_detail_api(
    request: Request,
    archive_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        data = get_archive_detail(db, user, archive_id)
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="fetch success", data=data)


@router.get("/exports/{archive_id}/download")
def download_archive_api(
    request: Request,
    archive_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        file_path = get_archive_download_path(db, user, archive_id)
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return FileResponse(path=file_path, filename=file_path.name)
