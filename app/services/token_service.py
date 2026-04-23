import secrets

from sqlmodel import Session, select

from app.core.constants import MANAGE_REVIEW_ROLES
from app.core.utils import json_dumps, utcnow
from app.models.reviewer_token import ReviewerToken
from app.models.user import User
from app.schemas.token import ActivateReviewerTokenRequest, CreateReviewerTokenRequest
from app.services.errors import ServiceError
from app.services.reviewer_scope_service import (
    is_datetime_expired,
    refresh_user_reviewer_state,
    sync_reviewer_token_expirations,
)
from app.services.serializers import serialize_reviewer_token
from app.services.system_log_service import write_system_log


def create_reviewer_token(db: Session, user: User, payload: CreateReviewerTokenRequest) -> dict:
    if user.role not in MANAGE_REVIEW_ROLES:
        raise ServiceError("permission denied", 1003)
    class_ids = sorted({int(item) for item in payload.class_ids})
    token = ReviewerToken(
        token=f"rvw_{secrets.token_urlsafe(16)}",
        token_type="reviewer",
        class_ids_json=json_dumps(class_ids),
        created_by=user.id,
        expires_at=payload.expired_at,
    )
    db.add(token)
    db.commit()
    db.refresh(token)
    write_system_log(db, action="token.create", actor_id=user.id, target_type="token", target_id=str(token.id))
    return serialize_reviewer_token(token)


def activate_reviewer_token(db: Session, user: User, payload: ActivateReviewerTokenRequest) -> dict:
    if user.role != "student":
        raise ServiceError("permission denied", 1003)
    sync_reviewer_token_expirations(db, auto_commit=True)
    token = db.exec(select(ReviewerToken).where(ReviewerToken.token == payload.token)).first()
    if not token:
        raise ServiceError("token not found", 1002)
    if token.status == "revoked":
        raise ServiceError("token revoked", 1000)
    if is_datetime_expired(token.expires_at):
        token.status = "expired"
        db.add(token)
        if token.activated_user_id:
            activated_user = db.get(User, token.activated_user_id)
            if activated_user:
                refresh_user_reviewer_state(db, activated_user)
        db.commit()
        raise ServiceError("token expired", 1000)

    if token.status == "active":
        if token.activated_user_id != user.id:
            raise ServiceError("token already activated", 1007)
    else:
        token.status = "active"
        token.activated_user_id = user.id
        token.activated_at = utcnow()
        token.revoked_at = None
        db.add(token)

    refresh_user_reviewer_state(db, user)
    db.commit()
    write_system_log(db, action="token.activate", actor_id=user.id, target_type="token", target_id=str(token.id))
    return {
        "token_id": token.id,
        "reviewer_token_id": user.reviewer_token_id,
        "status": token.status,
        "activated_user_id": token.activated_user_id,
        "activated_at": token.activated_at.isoformat() if token.activated_at else None,
        "is_reviewer": bool(user.is_reviewer),
    }


def list_tokens(
    db: Session,
    user: User,
    *,
    token_type: str | None,
    status: str | None,
    page: int,
    size: int,
) -> dict:
    sync_reviewer_token_expirations(db, auto_commit=True)
    if user.role in MANAGE_REVIEW_ROLES:
        stmt = select(ReviewerToken)
        if token_type:
            stmt = stmt.where(ReviewerToken.token_type == token_type)
        if status:
            stmt = stmt.where(ReviewerToken.status == status)
        total = len(db.exec(stmt).all())
        rows = db.exec(stmt.order_by(ReviewerToken.created_at.desc()).offset((page - 1) * size).limit(size)).all()
        return {
            "page": page,
            "size": size,
            "total": total,
            "list": [serialize_reviewer_token(row) for row in rows],
        }

    if user.role == "student":
        stmt = select(ReviewerToken).where(ReviewerToken.activated_user_id == user.id)
        if token_type:
            stmt = stmt.where(ReviewerToken.token_type == token_type)
        if status:
            stmt = stmt.where(ReviewerToken.status == status)
        else:
            stmt = stmt.where(ReviewerToken.status == "active")
        total = len(db.exec(stmt).all())
        rows = db.exec(stmt.order_by(ReviewerToken.created_at.desc()).offset((page - 1) * size).limit(size)).all()
        return {
            "page": page,
            "size": size,
            "total": total,
            "list": [serialize_reviewer_token(row) for row in rows],
        }

    raise ServiceError("permission denied", 1003)


def revoke_token(db: Session, user: User, token_id: int) -> None:
    if user.role not in MANAGE_REVIEW_ROLES:
        raise ServiceError("permission denied", 1003)
    token = db.get(ReviewerToken, token_id)
    if not token:
        raise ServiceError("token not found", 1002)
    token.status = "revoked"
    token.revoked_at = utcnow()
    db.add(token)

    if token.activated_user_id:
        activated_user = db.get(User, token.activated_user_id)
        if activated_user:
            refresh_user_reviewer_state(db, activated_user)

    db.commit()
    write_system_log(db, action="token.revoke", actor_id=user.id, target_type="token", target_id=str(token.id))


def unbind_token(db: Session, user: User, token_id: int) -> None:
    if user.role != "student":
        raise ServiceError("permission denied", 1003)

    token = db.exec(
        select(ReviewerToken).where(
            ReviewerToken.id == token_id,
            ReviewerToken.activated_user_id == user.id,
            ReviewerToken.status == "active",
        )
    ).first()
    if not token:
        raise ServiceError("token not found", 1002)

    token.status = "pending"
    token.activated_user_id = None
    token.activated_at = None
    token.revoked_at = None
    db.add(token)
    refresh_user_reviewer_state(db, user)
    db.commit()
    write_system_log(db, action="token.unbind", actor_id=user.id, target_type="token", target_id=str(token.id))
