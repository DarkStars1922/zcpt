from fastapi import APIRouter, Depends, Request
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
