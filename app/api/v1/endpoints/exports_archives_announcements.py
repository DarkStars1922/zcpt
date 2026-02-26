from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse
from sqlmodel import Session

from app.core.database import get_db
from app.core.responses import error_response, success_response
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.export_archive_announcement import (
    AnnouncementCreateRequest,
    ArchiveCreateRequest,
    TeacherExportCreateRequest,
)
from app.services.export_archive_announcement_service import (
    ExportArchiveAnnouncementError,
    create_announcement,
    create_archive,
    create_export_task,
    get_archive_download_file,
    get_archive_detail,
    get_export_task,
    list_announcements,
    list_archives,
)

router = APIRouter(tags=["teacher-archive-announcement"])


@router.post("/teacher/exports")
def create_teacher_export_api(
    request: Request,
    payload: TeacherExportCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        task = create_export_task(
            db,
            user,
            scope=payload.scope,
            output_format=payload.format,
            filters=payload.filters.model_dump(exclude_none=True),
        )
    except ExportArchiveAnnouncementError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)

    return success_response(
        request=request,
        message="导出任务已创建",
        data={
            "task_id": task.task_id,
            "status": task.status,
            "total_students": task.total_students,
            "total_applications": task.total_applications,
        },
    )


@router.get("/teacher/exports/{task_id}")
def get_teacher_export_api(
    request: Request,
    task_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        task = get_export_task(db, user, task_id=task_id)
    except ExportArchiveAnnouncementError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)

    base_url = str(request.base_url).rstrip("/")
    return success_response(
        request=request,
        message="获取成功",
        data={
            "task_id": task.task_id,
            "status": task.status,
            "scope": task.scope,
            "format": task.format,
            "filters": task.filters,
            "total_students": task.total_students,
            "total_applications": task.total_applications,
            "created_at": task.created_at.isoformat(),
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "download_url": f"{base_url}/api/v1/teacher/exports/{task.task_id}/download" if task.status == "success" else None,
        },
    )


@router.get("/teacher/exports/{task_id}/download")
def download_teacher_export_api(
    request: Request,
    task_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        task = get_export_task(db, user, task_id=task_id)
    except ExportArchiveAnnouncementError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)

    if task.status != "success" or not task.file_path:
        return error_response(request=request, code=1002, message="导出文件不存在")
    return FileResponse(path=task.file_path, filename=task.file_name or f"{task.task_id}.xlsx")


@router.post("/archives/exports")
def create_archive_api(
    request: Request,
    payload: ArchiveCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        archive = create_archive(
            db,
            user,
            export_task_id=payload.export_task_id,
            archive_name=payload.archive_name,
            term=payload.term,
            grade=payload.grade,
            class_ids=payload.class_ids,
        )
    except ExportArchiveAnnouncementError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)

    return success_response(
        request=request,
        message="归档创建成功",
        data={
            "archive_id": archive.archive_id,
            "archive_name": archive.archive_name,
            "export_task_id": archive.export_task_id,
            "term": archive.term,
            "grade": archive.grade,
            "class_ids": archive.class_ids,
            "is_announced": archive.is_announced,
            "created_at": archive.created_at.isoformat(),
        },
    )


@router.get("/archives/exports")
def list_archives_api(
    request: Request,
    term: str | None = Query(default=None),
    grade: int | None = Query(default=None),
    class_id: int | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        data = list_archives(db, user, term=term, grade=grade, class_id=class_id, page=page, size=size)
    except ExportArchiveAnnouncementError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)

    return success_response(request=request, message="获取成功", data=data)


@router.get("/archives/exports/{archive_id}/download")
def archive_download_api(
    request: Request,
    archive_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        file_path, file_name = get_archive_download_file(db, user, archive_id=archive_id)
    except ExportArchiveAnnouncementError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)

    return FileResponse(path=file_path, filename=file_name)


@router.get("/archives/exports/{archive_id}")
def archive_detail_api(
    request: Request,
    archive_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        data = get_archive_detail(db, user, archive_id=archive_id)
    except ExportArchiveAnnouncementError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="获取成功", data=data)


@router.post("/announcements")
def create_announcement_api(
    request: Request,
    payload: AnnouncementCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        announcement = create_announcement(
            db,
            user,
            title=payload.title,
            archive_id=payload.archive_id,
            start_at=payload.start_at,
            end_at=payload.end_at,
            content=payload.content,
        )
    except ExportArchiveAnnouncementError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)

    return success_response(
        request=request,
        message="公示发布成功",
        data={
            "id": announcement.id,
            "archive_id": announcement.archive_id,
            "title": announcement.title,
            "start_at": announcement.start_at.isoformat(),
            "end_at": announcement.end_at.isoformat(),
            "created_at": announcement.created_at.isoformat(),
        },
    )


@router.get("/announcements")
def list_announcements_api(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        data = list_announcements(db, user)
    except ExportArchiveAnnouncementError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="获取成功", data={"list": data, "total": len(data)})
