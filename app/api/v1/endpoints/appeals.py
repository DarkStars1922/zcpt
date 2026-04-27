from fastapi import APIRouter, Depends, Query, Request
from sqlmodel import Session

from app.core.database import get_db
from app.core.responses import error_response, success_response
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.appeal import AppealCreateRequest, AppealProcessRequest
from app.services.appeal_service import (
    create_appeal,
    delete_appeal,
    list_appeals,
    process_appeal,
    search_appeal_target_applications,
)
from app.services.errors import ServiceError

router = APIRouter(prefix="/appeals", tags=["appeals"])


@router.post("")
def create_appeal_api(
    request: Request,
    payload: AppealCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        data = create_appeal(db, user, payload)
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="提交成功", data=data)


@router.get("")
def list_appeals_api(
    request: Request,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=100),
    student_id: int | None = Query(default=None),
    status: str | None = Query(default=None),
    announcement_id: int | None = Query(default=None),
    student_name: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        data = list_appeals(
            db,
            user,
            page=page,
            size=size,
            student_id=student_id,
            status=status,
            announcement_id=announcement_id,
            student_name=student_name,
            keyword=keyword,
        )
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="获取成功", data=data)


@router.get("/application-options")
def search_application_options_api(
    request: Request,
    student_name: str | None = Query(default=None),
    student_id: int | None = Query(default=None),
    announcement_id: int | None = Query(default=None),
    appeal_id: int | None = Query(default=None),
    keyword: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        data = search_appeal_target_applications(
            db,
            user,
            student_name=student_name,
            student_id=student_id,
            announcement_id=announcement_id,
            appeal_id=appeal_id,
            keyword=keyword,
            limit=limit,
        )
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="获取成功", data=data)


@router.post("/{appeal_id}/process")
def process_appeal_api(
    request: Request,
    appeal_id: int,
    payload: AppealProcessRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        data = process_appeal(db, user, appeal_id, payload)
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="处理成功", data=data)


@router.delete("/{appeal_id}")
def delete_appeal_api(
    request: Request,
    appeal_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        delete_appeal(db, user, appeal_id)
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="删除成功", data={})
