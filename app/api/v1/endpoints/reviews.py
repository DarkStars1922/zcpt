from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from sqlmodel import Session

from app.core.database import get_db
from app.core.responses import error_response, success_response
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.review import ReviewBatchDecisionRequest, ReviewDecisionRequest
from app.services.review_service import (
    ReviewError,
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
def pending_api(
    request: Request,
    class_id: int | None = Query(default=None),
    category: str | None = Query(default=None),
    sub_type: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=100),
    keyword: str | None = Query(default=None),
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
            keyword=keyword,
            page=page,
            size=size,
        )
    except ReviewError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)

    return success_response(request=request, message="获取成功", data=data)


@router.get("/pending/category-summary")
def pending_category_summary_api(
    request: Request,
    class_id: int | None = Query(default=None),
    term: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        data = get_pending_category_summary(db, user, class_id=class_id, term=term)
    except ReviewError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)

    return success_response(request=request, message="获取成功", data=data)


@router.get("/pending/by-category")
def pending_by_category_api(
    request: Request,
    class_id: int | None = Query(default=None),
    category: str = Query(...),
    sub_type: str | None = Query(default=None),
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
            term=term,
            page=page,
            size=size,
        )
    except ReviewError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)

    return success_response(request=request, message="获取成功", data=data)


@router.get("/history")
def review_history_api(
    request: Request,
    class_id: int | None = Query(default=None),
    result: str | None = Query(default=None),
    from_at: datetime | None = Query(default=None, alias="from"),
    to_at: datetime | None = Query(default=None, alias="to"),
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
            from_at=from_at,
            to_at=to_at,
            page=page,
            size=size,
        )
    except ReviewError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)

    return success_response(request=request, message="获取成功", data=data)


@router.get("/pending-count")
def pending_count_api(
    request: Request,
    class_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        data = get_pending_count(db, user, class_id=class_id)
    except ReviewError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)

    return success_response(request=request, message="获取成功", data=data)


@router.get("/{application_id}")
def review_detail_api(
    request: Request,
    application_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        data = get_review_detail(db, user, application_id=application_id)
    except ReviewError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)

    return success_response(request=request, message="获取成功", data=data)


@router.post("/batch-decision")
def review_batch_decision_api(
    request: Request,
    payload: ReviewBatchDecisionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        data = submit_batch_review_decision(
            db,
            user,
            application_ids=payload.application_ids,
            decision=payload.decision,
            comment=payload.comment,
            reason_code=payload.reason_code,
            reason_text=payload.reason_text,
        )
    except ReviewError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)

    return success_response(
        request=request,
        message="批量审核完成",
        data=data,
    )


@router.post("/{application_id}/decision")
def review_decision_api(
    request: Request,
    application_id: int,
    payload: ReviewDecisionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        application, review_record = submit_review_decision(
            db,
            user,
            application_id=application_id,
            decision=payload.decision,
            comment=payload.comment,
            reason_code=payload.reason_code,
            reason_text=payload.reason_text,
        )
    except ReviewError as exc:
        return error_response(request=request, code=exc.code, message=exc.message)

    return success_response(
        request=request,
        message="审核完成",
        data={
            "application_id": application.id,
            "status": application.status,
            "review_id": review_record.id,
            "reviewed_at": review_record.created_at.isoformat(),
        },
    )
