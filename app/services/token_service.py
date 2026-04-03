import secrets

from sqlmodel import Session, select

from app.core.constants import MANAGE_REVIEW_ROLES
from app.core.utils import json_dumps, utcnow
from app.models.reviewer_token import ReviewerToken
from app.models.user import User
from app.schemas.token import ActivateReviewerTokenRequest, CreateReviewerTokenRequest
from app.services.errors import ServiceError
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
    token = db.exec(select(ReviewerToken).where(ReviewerToken.token == payload.token)).first()
    if not token:
        raise ServiceError("token not found", 1002)
    if token.status == "revoked":
        raise ServiceError("token revoked", 1000)
    if token.status == "active":
        raise ServiceError("token already activated", 1007)
    if token.expires_at and token.expires_at < utcnow():
        token.status = "expired"
        db.add(token)
        db.commit()
        raise ServiceError("token expired", 1000)

    token.status = "active"
    token.activated_user_id = user.id
    token.activated_at = utcnow()
    db.add(token)
    user.is_reviewer = True
    user.reviewer_token_id = token.id
    user.updated_at = utcnow()
    db.add(user)
    db.commit()
    write_system_log(db, action="token.activate", actor_id=user.id, target_type="token", target_id=str(token.id))
    return {
        "token_id": token.id,
        "reviewer_token_id": token.id,
        "status": token.status,
        "activated_user_id": token.activated_user_id,
        "activated_at": token.activated_at.isoformat() if token.activated_at else None,
        "is_reviewer": True,
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
    if user.role not in MANAGE_REVIEW_ROLES:
        raise ServiceError("permission denied", 1003)
    stmt = select(ReviewerToken)
    if token_type:
        stmt = stmt.where(ReviewerToken.token_type == token_type)
    if status:
        stmt = stmt.where(ReviewerToken.status == status)
    rows = db.exec(stmt.order_by(ReviewerToken.created_at.desc()).offset((page - 1) * size).limit(size)).all()
    total = len(db.exec(stmt).all())
    return {
        "page": page,
        "size": size,
        "total": total,
        "list": [serialize_reviewer_token(row) for row in rows],
    }


def revoke_token(db: Session, user: User, token_id: int) -> None:
    if user.role not in MANAGE_REVIEW_ROLES:
        raise ServiceError("permission denied", 1003)
    token = db.get(ReviewerToken, token_id)
    if not token:
        raise ServiceError("token not found", 1002)
    token.status = "revoked"
    token.revoked_at = utcnow()
    db.add(token)
    db.commit()
    write_system_log(db, action="token.revoke", actor_id=user.id, target_type="token", target_id=str(token.id))
