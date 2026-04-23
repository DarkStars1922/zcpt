from fastapi import APIRouter, Depends, Request
from sqlmodel import Session

from app.core.database import get_db
from app.core.responses import error_response, success_response
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.user import UserUpdateRequest
from app.services.errors import ServiceError
from app.services.user_service import get_me, update_me

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me")
def get_me_api(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return success_response(request=request, message="fetch success", data=get_me(db, user))


@router.put("/me")
def update_me_api(
    request: Request,
    payload: UserUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        data = update_me(db, user, payload)
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="update success", data=data)
