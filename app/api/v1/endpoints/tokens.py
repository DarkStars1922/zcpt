from fastapi import APIRouter, Depends, Query, Request
from sqlmodel import Session

from app.core.database import get_db
from app.core.responses import error_response, success_response
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.token import ActivateReviewerTokenRequest, CreateReviewerTokenRequest
from app.services.errors import ServiceError
from app.services.token_service import (
    activate_reviewer_token,
    create_reviewer_token,
    list_tokens,
    revoke_token,
    unbind_token,
)

router = APIRouter(prefix="/tokens", tags=["tokens"])


@router.post("/reviewer")
def create_reviewer_token_api(
    request: Request,
    payload: CreateReviewerTokenRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        data = create_reviewer_token(db, user, payload)
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="create success", data=data)


@router.post("/reviewer/activate")
def activate_reviewer_token_api(
    request: Request,
    payload: ActivateReviewerTokenRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        data = activate_reviewer_token(db, user, payload)
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="activate success", data=data)


@router.get("")
def list_tokens_api(
    request: Request,
    type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        data = list_tokens(db, user, token_type=type, status=status, page=page, size=size)
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="fetch success", data=data)


@router.post("/{token_id}/revoke")
def revoke_token_api(
    request: Request,
    token_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        revoke_token(db, user, token_id)
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="revoke success", data={})


@router.post("/{token_id}/unbind")
def unbind_token_api(
    request: Request,
    token_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        unbind_token(db, user, token_id)
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="unbind success", data={})
