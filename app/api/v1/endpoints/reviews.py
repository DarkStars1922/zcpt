from fastapi import APIRouter, Depends, Query, Request
from sqlmodel import Session

from app.core.database import get_db
from app.core.responses import error_response, success_response
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.review import BatchReviewDecisionRequest, ReviewDecisionRequest
from app.services.errors import ServiceError
from app.services.review_service import (
    get_pending_by_category,
    get_pending_category_summary,
    get_pending_count,
    get_pending_list,
    get_review_detail,
    get_review_history,
    submit_batch_review_decision,
    submit_review_decision,
)

router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.get("/pending")
def get_pending_api(
    request: Request,
    class_id: int | None = Query(default=None),
    category: str | None = Query(default=None),
    sub_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        data = get_pending_list(
            db,
            user,
            class_id=class_id,
            category=category,
            sub_type=sub_type,
            status=status,
            keyword=keyword,
            page=page,
            size=size,
        )
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="获取成功", data=data)


@router.get("/pending/category-summary")
def get_pending_summary_api(
    request: Request,
    class_id: int | None = Query(default=None),
    term: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        data = get_pending_category_summary(db, user, class_id=class_id, term=term)
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="获取成功", data=data)


@router.get("/pending/by-category")
def get_pending_by_category_api(
    request: Request,
    category: str = Query(...),
    class_id: int | None = Query(default=None),
    sub_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    term: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        data = get_pending_by_category(
            db,
            user,
            class_id=class_id,
            category=category,
            sub_type=sub_type,
            status=status,
            term=term,
            page=page,
            size=size,
        )
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="获取成功", data=data)


@router.get("/pending-count")
def get_pending_count_api(
    request: Request,
    class_id: int | None = Query(default=None),
    category: str | None = Query(default=None),
    sub_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        data = get_pending_count(db, user, class_id=class_id, category=category, sub_type=sub_type, status=status)
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="获取成功", data=data)


@router.get("/history")
def get_history_api(
    request: Request,
    class_id: int | None = Query(default=None),
    result: str | None = Query(default=None),
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        data = get_review_history(
            db,
            user,
            class_id=class_id,
            result=result,
            from_at=from_,
            to_at=to,
            page=page,
            size=size,
        )
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="获取成功", data=data)


@router.get("/{application_id}")
def get_review_detail_api(
    request: Request,
    application_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        data = get_review_detail(db, user, application_id)
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="获取成功", data=data)


@router.post("/{application_id}/decision")
def submit_review_decision_api(
    request: Request,
    application_id: int,
    payload: ReviewDecisionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        data = submit_review_decision(db, user, application_id, payload)
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="审核完成", data=data)


@router.post("/batch-decision")
def submit_batch_review_decision_api(
    request: Request,
    payload: BatchReviewDecisionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        data = submit_batch_review_decision(db, user, payload)
    except ServiceError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)
    return success_response(request=request, message="批量审核完成", data=data)
