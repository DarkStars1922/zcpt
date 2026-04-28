from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse
from sqlmodel import Session

from app.core.database import get_db
from app.core.responses import error_response, success_response
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.announcement import AnnouncementCreateRequest, AnnouncementUpdateRequest
from app.services.announcement_service import (
    close_announcement,
    create_announcement,
    delete_announcement,
    generate_my_announcement_story_copy,
    get_announcement_download_path,
    get_announcement_public_application_detail,
    get_announcement_public_application_file_path,
    get_my_announcement_report,
    list_announcement_public_applications,
    list_announcements,
    reopen_announcement,
    update_announcement,
)
from app.services.errors import ServiceError

router = APIRouter(prefix="/announcements", tags=["announcements"])


@router.get("")
def list_announcements_api(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        data = list_announcements(db, user)
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="获取成功", data=data)


@router.post("")
def create_announcement_api(
    request: Request,
    payload: AnnouncementCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        data = create_announcement(db, user, payload)
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="发布成功", data=data)


@router.get("/{announcement_id}/my-report")
def get_my_announcement_report_api(
    request: Request,
    announcement_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        data = get_my_announcement_report(db, user, announcement_id)
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="获取成功", data=data)


@router.post("/{announcement_id}/my-report/story-copy")
def generate_my_announcement_story_copy_api(
    request: Request,
    announcement_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        data = generate_my_announcement_story_copy(db, user, announcement_id)
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="生成成功", data=data)


@router.get("/{announcement_id}/applications")
def list_announcement_public_applications_api(
    request: Request,
    announcement_id: int,
    keyword: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        data = list_announcement_public_applications(
            db,
            user,
            announcement_id,
            keyword=keyword,
            page=page,
            size=size,
        )
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="获取成功", data=data)


@router.get("/{announcement_id}/applications/{application_id}")
def get_announcement_public_application_detail_api(
    request: Request,
    announcement_id: int,
    application_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        data = get_announcement_public_application_detail(db, user, announcement_id, application_id)
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="获取成功", data=data)


@router.get("/{announcement_id}/applications/{application_id}/files/{file_id}")
def get_announcement_public_application_file_api(
    request: Request,
    announcement_id: int,
    application_id: int,
    file_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        file_path, filename = get_announcement_public_application_file_path(
            db,
            user,
            announcement_id,
            application_id,
            file_id,
        )
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return FileResponse(path=file_path, filename=filename or file_path.name)


@router.get("/{announcement_id}/download")
def download_announcement_api(
    request: Request,
    announcement_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        file_path = get_announcement_download_path(db, user, announcement_id)
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return FileResponse(path=file_path, filename=file_path.name)


@router.put("/{announcement_id}")
def update_announcement_api(
    request: Request,
    announcement_id: int,
    payload: AnnouncementUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        data = update_announcement(db, user, announcement_id, payload)
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="更新成功", data=data)


@router.post("/{announcement_id}/close")
def close_announcement_api(
    request: Request,
    announcement_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        data = close_announcement(db, user, announcement_id)
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="关闭成功", data=data)


@router.post("/{announcement_id}/reopen")
def reopen_announcement_api(
    request: Request,
    announcement_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        data = reopen_announcement(db, user, announcement_id)
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="鍚敤鎴愬姛", data=data)


@router.delete("/{announcement_id}")
def delete_announcement_api(
    request: Request,
    announcement_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        delete_announcement(db, user, announcement_id)
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="删除成功", data={})
