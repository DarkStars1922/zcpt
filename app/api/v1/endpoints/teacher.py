from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import FileResponse
from sqlmodel import Session

from app.core.database import get_db
from app.core.responses import error_response, success_response
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.archive import ArchiveExportCreateRequest
from app.schemas.review import TeacherRecheckRequest
from app.schemas.teacher_insight import TeacherInsightAnalyzeRequest
from app.services.archive_service import create_teacher_export_task, get_export_file_path, get_export_task
from app.services.errors import ServiceError
from app.services.teacher_service import (
    archive_applications,
    get_class_statistics,
    get_statistics,
    get_student_statistics,
    list_teacher_applications,
    recheck_application,
)
from app.services.teacher_insight_service import analyze_teacher_insights

router = APIRouter(prefix="/teacher", tags=["teacher"])


@router.get("/applications")
def list_teacher_applications_api(
    request: Request,
    grade: int | None = Query(default=None),
    class_id: int | None = Query(default=None),
    status: str | None = Query(default=None),
    category: str | None = Query(default=None),
    sub_type: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        data = list_teacher_applications(
            db,
            user,
            grade=grade,
            class_id=class_id,
            status=status,
            category=category,
            sub_type=sub_type,
            keyword=keyword,
            page=page,
            size=size,
        )
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="fetch success", data=data)


@router.post("/applications/{application_id}/recheck")
def recheck_application_api(
    request: Request,
    application_id: int,
    payload: TeacherRecheckRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        data = recheck_application(db, user, application_id, payload)
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="recheck success", data=data)


@router.post("/applications/archive")
def archive_applications_api(
    request: Request,
    payload: dict,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        data = archive_applications(db, user, payload.get("application_ids") or [])
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="archive success", data=data)


@router.get("/statistics")
def get_statistics_api(
    request: Request,
    grade: int | None = Query(default=None),
    class_id: int | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        data = get_statistics(db, user, grade=grade, class_id=class_id)
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="fetch success", data=data)


@router.get("/statistics/classes")
def get_class_statistics_api(
    request: Request,
    grade: int | None = Query(default=None),
    class_id: int | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        data = get_class_statistics(db, user, grade=grade, class_id=class_id)
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="fetch success", data=data)


@router.get("/statistics/students")
def get_student_statistics_api(
    request: Request,
    grade: int | None = Query(default=None),
    class_id: int | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        data = get_student_statistics(db, user, grade=grade, class_id=class_id)
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="fetch success", data=data)


@router.post("/insights/analyze")
def analyze_teacher_insights_api(
    request: Request,
    payload: TeacherInsightAnalyzeRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        data = analyze_teacher_insights(
            db,
            user,
            grade=payload.grade,
            class_id=payload.class_id,
            class_ids=payload.class_ids,
            max_risk_students=payload.max_risk_students,
        )
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="analysis success", data=data)


@router.post("/exports")
def create_export_api(
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


@router.get("/exports/{task_id}")
def get_export_task_api(
    request: Request,
    task_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        data = get_export_task(db, user, task_id)
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="fetch success", data=data)


@router.get("/exports/{task_id}/download")
def download_export_api(
    request: Request,
    task_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        file_path = get_export_file_path(db, user, task_id)
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return FileResponse(path=file_path, filename=file_path.name)
