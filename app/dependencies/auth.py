from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session

from app.core.database import get_db
from app.models.user import User
from app.services.auth_service import get_current_user_by_access_token
from app.services.errors import ServiceError

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=401, detail={"code": 1004, "message": "未登录或 token 缺失"})

    token = credentials.credentials
    try:
        return get_current_user_by_access_token(db, token)
    except ServiceError as exc:
        raise HTTPException(status_code=401, detail={"code": exc.code, "message": exc.message}) from exc


def get_current_access_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> str:
    if credentials is None:
        raise HTTPException(status_code=401, detail={"code": 1004, "message": "未登录或 token 缺失"})
    return credentials.credentials


def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User | None:
    if credentials is None:
        return None
    try:
        return get_current_user_by_access_token(db, credentials.credentials)
    except ServiceError:
        return None
