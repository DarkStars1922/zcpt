from fastapi import APIRouter, Depends, Query, Request
from sqlmodel import Session

from app.core.database import get_db
from app.core.responses import error_response, success_response
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.system import (
    AdminUserCreateRequest,
    AdminUserUpdateRequest,
    AwardDictCreateRequest,
    AwardDictUpdateRequest,
    ClassCreateRequest,
    ClassUpdateRequest,
    SystemConfigUpdateRequest,
)
from app.services.errors import ServiceError
from app.services.system_service import (
    create_user_by_admin,
    create_class,
    create_award_dict,
    delete_class,
    delete_user_by_admin,
    delete_award_dict,
    get_system_configs,
    get_system_logs,
    list_classes,
    list_users,
    list_award_dicts,
    update_user_by_admin,
    update_class,
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


@router.get("/users")
def list_users_api(
    request: Request,
    role: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        data = list_users(db, user, role=role, keyword=keyword, page=page, size=size)
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="获取成功", data=data)


@router.post("/users")
def create_user_api(
    request: Request,
    payload: AdminUserCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        data = create_user_by_admin(db, user, payload)
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="创建成功", data=data)


@router.put("/users/{user_id}")
def update_user_api(
    request: Request,
    user_id: int,
    payload: AdminUserUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        data = update_user_by_admin(db, user, user_id, payload)
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="更新成功", data=data)


@router.delete("/users/{user_id}")
def delete_user_api(
    request: Request,
    user_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        delete_user_by_admin(db, user, user_id)
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="删除成功", data={})


@router.get("/classes/public")
def list_public_classes_api(request: Request, db: Session = Depends(get_db)):
    try:
        data = list_classes(db, None, public_only=True)
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="获取成功", data=data)


@router.get("/classes")
def list_classes_api(
    request: Request,
    include_deleted: bool = Query(default=False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        data = list_classes(db, user, include_deleted=include_deleted)
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="获取成功", data=data)


@router.post("/classes")
def create_class_api(
    request: Request,
    payload: ClassCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        data = create_class(db, user, payload)
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="创建成功", data=data)


@router.put("/classes/{class_id}")
def update_class_api(
    request: Request,
    class_id: int,
    payload: ClassUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        data = update_class(db, user, class_id, payload)
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="更新成功", data=data)


@router.delete("/classes/{class_id}")
def delete_class_api(
    request: Request,
    class_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        delete_class(db, user, class_id)
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="删除成功", data={})


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
