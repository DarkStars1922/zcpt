from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session

from app.core.database import get_db
from app.core.responses import error_response, success_response
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.auth import LoginRequest, LogoutRequest, RefreshRequest, RegisterRequest
from app.services.auth_service import (
    AuthError,
    access_token_expire_seconds,
    login_user,
    refresh_access_token,
    register_user,
    revoke_refresh_token,
)

router = APIRouter()


@router.post("/register")
def register(request: Request, payload: RegisterRequest, db: Session = Depends(get_db)):
    try:
        user = register_user(
            db,
            account=payload.account,
            password=payload.password,
            name=payload.name,
            role=payload.role,
            class_id=payload.class_id,
            email=payload.email,
            phone=payload.phone,
        )
    except AuthError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)

    return success_response(
        request=request,
        message="注册成功",
        data={
            "user": {
                "id": user.id,
                "name": user.name,
                "role": user.role,
                "class_id": user.class_id,
            }
        },
    )


@router.post("/login")
def login(request: Request, payload: LoginRequest, db: Session = Depends(get_db)):
    try:
        user, access_token, refresh_token = login_user(db, account=payload.account, password=payload.password)
    except AuthError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)

    return success_response(
        request=request,
        message="登录成功",
        data={
            "user": {
                "id": user.id,
                "name": user.name,
                "role": user.role,
                "class_id": user.class_id,
            },
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": access_token_expire_seconds(),
        },
    )


@router.post("/refresh")
def refresh_token(request: Request, payload: RefreshRequest, db: Session = Depends(get_db)):
    try:
        access_token = refresh_access_token(db, refresh_token=payload.refresh_token)
    except AuthError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)

    return success_response(
        request=request,
        message="刷新成功",
        data={"access_token": access_token, "expires_in": access_token_expire_seconds()},
    )


@router.post("/logout")
def logout(
    request: Request,
    payload: LogoutRequest,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        revoke_refresh_token(db, refresh_token=payload.refresh_token)
    except AuthError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)

    return success_response(request=request, message="退出成功", data={})
