from fastapi import APIRouter, Depends, Query, Request
from sqlmodel import Session

from app.core.database import get_db
from app.core.responses import error_response, success_response
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.application import ApplicationCreateRequest, ApplicationUpdateRequest
from app.services.application_service import (
    ApplicationError,
    create_application,
    get_application_detail,
    get_my_by_category,
    get_my_category_summary,
    soft_delete_application,
    update_application,
    withdraw_application,
)

router = APIRouter(prefix="/applications", tags=["applications"])


@router.post("")
def create_application_api(request: Request, payload: ApplicationCreateRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        row = create_application(db, user, payload)
    except ApplicationError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)

    return success_response(
        request=request,
        message="创建成功",
        data={
            "id": row.id,
            "status": row.status,
            "item_score": row.item_score,
            "score_rule_version": row.score_rule_version,
            "created_at": row.created_at.isoformat(),
        },
    )


@router.get("/my/category-summary")
def category_summary_api(
    request: Request,
    term: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        data = get_my_category_summary(db, user, term=term)
    except ApplicationError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)

    return success_response(request=request, message="获取成功", data=data)


@router.get("/my/by-category")
def by_category_api(
    request: Request,
    category: str = Query(...),
    sub_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    term: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        data = get_my_by_category(
            db,
            user,
            category=category,
            sub_type=sub_type,
            status=status,
            term=term,
            page=page,
            size=size,
        )
    except ApplicationError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)

    return success_response(request=request, message="获取成功", data=data)


@router.get("/{application_id}")
def detail_api(
    request: Request,
    application_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        row = get_application_detail(db, user, application_id)
    except ApplicationError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)

    return success_response(
        request=request,
        message="获取成功",
        data={
            "id": row.id,
            "category": row.category,
            "sub_type": row.sub_type,
            "award_uid": row.award_uid,
            "title": row.title,
            "description": row.description,
            "occurred_at": row.occurred_at.isoformat(),
            "attachments": row.attachments,
            "status": row.status,
            "item_score": row.item_score,
            "comment": row.comment,
            "version": row.version,
            "created_at": row.created_at.isoformat(),
        },
    )


@router.put("/{application_id}")
def update_api(
    request: Request,
    application_id: int,
    payload: ApplicationUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        row = update_application(db, user, application_id, payload)
    except ApplicationError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)

    return success_response(
        request=request,
        message="更新成功",
        data={"id": row.id, "status": row.status, "version": row.version, "updated_at": row.updated_at.isoformat()},
    )


@router.post("/{application_id}/withdraw")
def withdraw_api(
    request: Request,
    application_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        row = withdraw_application(db, user, application_id)
    except ApplicationError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)

    return success_response(
        request=request,
        message="撤回成功",
        data={"id": row.id, "status": row.status, "version": row.version},
    )


@router.delete("/{application_id}")
def delete_api(
    request: Request,
    application_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        soft_delete_application(db, user, application_id)
    except ApplicationError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)

    return success_response(request=request, message="删除成功", data={})
