from fastapi import APIRouter, Depends, Query, Request
from sqlmodel import Session

from app.core.database import get_db
from app.core.responses import error_response, success_response
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.services.ai_audit_service import get_ai_logs, get_ai_report
from app.services.errors import ServiceError

router = APIRouter(prefix="/ai-audits", tags=["ai-audits"])


@router.get("/{application_id}/report")
def get_ai_report_api(
    request: Request,
    application_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        data = get_ai_report(db, user, application_id)
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="获取成功", data=data)


@router.get("/logs")
def get_ai_logs_api(
    request: Request,
    result: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        data = get_ai_logs(db, user, result=result, page=page, size=size)
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="获取成功", data=data)
