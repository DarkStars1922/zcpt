from fastapi import APIRouter, Depends, Query, Request
from sqlmodel import Session

from app.core.database import get_db
from app.core.responses import error_response, success_response
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.system import AwardDictCreateRequest, AwardDictUpdateRequest, SystemConfigUpdateRequest
from app.services.errors import ServiceError
from app.services.system_service import (
    create_award_dict,
    delete_award_dict,
    get_system_configs,
    get_system_logs,
    list_award_dicts,
    update_award_dict,
    update_system_config,
)

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/configs")
def get_system_configs_api(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        data = get_system_configs(db, user)
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="获取成功", data=data)


@router.put("/configs")
def update_system_configs_api(
    request: Request,
    payload: SystemConfigUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        data = update_system_config(db, user, payload)
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="更新成功", data=data)


@router.get("/logs")
def get_system_logs_api(
    request: Request,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=100),
    action: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        data = get_system_logs(db, user, page=page, size=size, action=action)
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="获取成功", data=data)


@router.get("/award-dicts")
def list_award_dicts_api(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        data = list_award_dicts(db, user)
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="获取成功", data=data)


@router.post("/award-dicts")
def create_award_dict_api(
    request: Request,
    payload: AwardDictCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        data = create_award_dict(db, user, payload)
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="创建成功", data=data)


@router.put("/award-dicts/{award_id}")
def update_award_dict_api(
    request: Request,
    award_id: int,
    payload: AwardDictUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        data = update_award_dict(db, user, award_id, payload)
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="更新成功", data=data)


@router.delete("/award-dicts/{award_id}")
def delete_award_dict_api(
    request: Request,
    award_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        delete_award_dict(db, user, award_id)
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="删除成功", data={})
