from fastapi import APIRouter, Depends, Query, Request
from sqlmodel import Session

from app.core.database import get_db
from app.core.responses import error_response, success_response
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.token import ReviewerTokenActivateRequest, ReviewerTokenCreateRequest
from app.services.token_service import (
    TokenError,
    activate_reviewer_token,
    create_reviewer_token,
    list_tokens,
    revoke_token,
)

router = APIRouter(prefix="/tokens", tags=["tokens"])


@router.post("/reviewer")
def create_reviewer_token_api(
    request: Request,
    payload: ReviewerTokenCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        row = create_reviewer_token(db, user, class_ids=payload.class_ids, expired_at=payload.expired_at)
    except TokenError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)

    return success_response(
        request=request,
        message="创建成功",
        data={
            "token_id": row.id,
            "token": row.token,
            "type": row.token_type,
            "class_ids": row.class_ids,
            "expired_at": row.expired_at.isoformat(),
        },
    )


@router.post("/reviewer/activate")
def activate_reviewer_token_api(
    request: Request,
    payload: ReviewerTokenActivateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        row = activate_reviewer_token(db, user, token=payload.token)
    except TokenError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)

    return success_response(
        request=request,
        message="激活成功",
        data={
            "token_id": row.id,
            "status": "active",
            "activated_user_id": row.activated_user_id,
            "activated_at": row.activated_at.isoformat() if row.activated_at else None,
            "is_reviewer": user.is_reviewer,
            "reviewer_token_id": user.reviewer_token_id,
        },
    )


@router.get("")
def list_tokens_api(
    request: Request,
    type: str = Query(default="reviewer"),
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        data = list_tokens(db, user, token_type=type, status=status, page=page, size=size)
    except TokenError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)

    return success_response(request=request, message="获取成功", data=data)


@router.post("/{token_id}/revoke")
def revoke_token_api(
    request: Request,
    token_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        revoke_token(db, user, token_id=token_id)
    except TokenError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)

    return success_response(request=request, message="失效成功", data={})
