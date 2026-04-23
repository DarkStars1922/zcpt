from sqlmodel import Session
from sqlmodel import select

from app.core.utils import utcnow
from app.models.reviewer_token import ReviewerToken
from app.models.user import User
from app.schemas.user import UserUpdateRequest
from app.services.reviewer_scope_service import (
    list_active_reviewer_tokens_for_user,
    refresh_user_reviewer_state,
    sync_reviewer_token_expirations,
)
from app.services.serializers import serialize_reviewer_token, serialize_user
from app.services.system_log_service import write_system_log


def get_me(db: Session, user: User) -> dict:
    if user.role == "student":
        refresh_user_reviewer_state(db, user)
        db.commit()
        db.refresh(user)
    else:
        sync_reviewer_token_expirations(db, auto_commit=True)
    return serialize_user(user, tokens=_list_tokens_for_user(db, user))


def update_me(db: Session, user: User, payload: UserUpdateRequest) -> dict:
    if "email" in payload.model_fields_set:
        user.email = payload.email
    if "phone" in payload.model_fields_set:
        user.phone = payload.phone
    user.updated_at = utcnow()
    db.add(user)
    db.commit()
    db.refresh(user)
    write_system_log(db, action="user.update_me", actor_id=user.id, target_type="user", target_id=str(user.id))
    return serialize_user(user, tokens=_list_tokens_for_user(db, user))


def _list_tokens_for_user(db: Session, user: User) -> list[dict]:
    if user.role == "student":
        rows = list_active_reviewer_tokens_for_user(db, user)
        return [serialize_reviewer_token(row) for row in rows]

    if user.role in {"teacher", "admin"}:
        rows = db.exec(
            select(ReviewerToken)
            .where(ReviewerToken.created_by == user.id)
            .order_by(ReviewerToken.created_at.desc())
        ).all()
        return [serialize_reviewer_token(row) for row in rows]

    return []
