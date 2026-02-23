from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session

from app.core.database import get_db
from app.models.user import User
from app.services.auth_service import AuthError, get_current_user_by_access_token

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
    except AuthError as exc:
        raise HTTPException(status_code=401, detail={"code": exc.code, "message": exc.message}) from exc
