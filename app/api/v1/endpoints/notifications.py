from fastapi import APIRouter, Depends, Query, Request
from sqlmodel import Session

from app.core.database import get_db
from app.core.responses import error_response, success_response
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.notification import RejectEmailRequest
from app.services.errors import ServiceError
from app.services.notification_service import get_email_logs, queue_reject_email

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.post("/reject-email")
def queue_reject_email_api(
    request: Request,
    payload: RejectEmailRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        data = queue_reject_email(db, user, payload)
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="发送成功", data=data)


@router.get("/email-logs")
def get_email_logs_api(
    request: Request,
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        data = get_email_logs(db, user, status=status, page=page, size=size)
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="获取成功", data=data)
