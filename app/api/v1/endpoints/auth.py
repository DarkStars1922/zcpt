from fastapi import APIRouter, Depends, Request
from sqlmodel import Session

from app.core.database import get_db
from app.core.responses import error_response, success_response
from app.dependencies.auth import get_current_access_token, get_current_user
from app.models.user import User
from app.schemas.auth import ChangePasswordRequest, LoginRequest, LogoutRequest, RefreshRequest, RegisterRequest
from app.services.auth_service import (
    access_token_expire_seconds,
    change_password,
    login_user,
    logout_user,
    refresh_access_token,
    register_user,
)
from app.services.errors import ServiceError
from app.services.serializers import serialize_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register")
def register_api(request: Request, payload: RegisterRequest, db: Session = Depends(get_db)):
    try:
        user = register_user(db, **payload.model_dump())
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="register success", data={"user": serialize_user(user)})


@router.post("/login")
def login_api(request: Request, payload: LoginRequest, db: Session = Depends(get_db)):
    try:
        user, access_token, refresh_token = login_user(db, **payload.model_dump())
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(
        request=request,
        message="login success",
        data={
            "user": user,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": access_token_expire_seconds(),
        },
    )


@router.post("/refresh")
def refresh_api(request: Request, payload: RefreshRequest, db: Session = Depends(get_db)):
    try:
        access_token = refresh_access_token(db, refresh_token=payload.refresh_token)
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(
        request=request,
        message="refresh success",
        data={"access_token": access_token, "expires_in": access_token_expire_seconds()},
    )


@router.post("/logout")
def logout_api(
    request: Request,
    payload: LogoutRequest,
    _: User = Depends(get_current_user),
    access_token: str = Depends(get_current_access_token),
    db: Session = Depends(get_db),
):
    try:
        logout_user(db, access_token=access_token, refresh_token=payload.refresh_token)
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="logout success", data={})


@router.post("/change-password")
def change_password_api(
    request: Request,
    payload: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    access_token: str = Depends(get_current_access_token),
    db: Session = Depends(get_db),
):
    try:
        change_password(db, user=user, access_token=access_token, payload=payload)
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="password updated", data={})
