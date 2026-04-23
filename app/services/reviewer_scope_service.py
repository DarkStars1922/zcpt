from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Session, select

from app.core.constants import REVIEWER_TOKEN_STATUS_ACTIVE, REVIEWER_TOKEN_STATUS_EXPIRED
from app.core.utils import json_loads, utcnow
from app.models.reviewer_token import ReviewerToken
from app.models.user import User

EXPIRE_CANDIDATE_STATUSES = {"pending", "active"}


def list_active_reviewer_tokens_for_user(db: Session, user: User) -> list[ReviewerToken]:
    if user.role != "student":
        return []
    now = utcnow()
    changed = sync_reviewer_token_expirations(db, activated_user_id=user.id, auto_commit=False, now=now)
    tokens = _query_active_tokens_for_user(db, user.id)

    expected_is_reviewer = bool(tokens)
    expected_reviewer_token_id = tokens[0].id if tokens else None
    user_state_changed = (
        bool(user.is_reviewer) != expected_is_reviewer or user.reviewer_token_id != expected_reviewer_token_id
    )
    if changed or user_state_changed:
        user.is_reviewer = expected_is_reviewer
        user.reviewer_token_id = expected_reviewer_token_id
        user.updated_at = now
        db.add(user)
        db.commit()
    return tokens


def get_active_reviewer_class_ids(db: Session, user: User) -> list[int]:
    class_ids: set[int] = set()
    for token in list_active_reviewer_tokens_for_user(db, user):
        for item in json_loads(token.class_ids_json, []):
            try:
                class_ids.add(int(item))
            except (TypeError, ValueError):
                continue
    return sorted(class_ids)


def refresh_user_reviewer_state(db: Session, user: User) -> None:
    if user.role != "student":
        user.is_reviewer = False
        user.reviewer_token_id = None
        user.updated_at = utcnow()
        db.add(user)
        return

    now = utcnow()
    sync_reviewer_token_expirations(db, activated_user_id=user.id, auto_commit=False, now=now)
    tokens = _query_active_tokens_for_user(db, user.id)
    user.is_reviewer = bool(tokens)
    user.reviewer_token_id = tokens[0].id if tokens else None
    user.updated_at = now
    db.add(user)


def sync_reviewer_token_expirations(
    db: Session,
    *,
    activated_user_id: int | None = None,
    auto_commit: bool = True,
    now: datetime | None = None,
) -> bool:
    now_value = _normalize_datetime(now or utcnow())
    stmt = select(ReviewerToken).where(
        ReviewerToken.status.in_(tuple(EXPIRE_CANDIDATE_STATUSES)),
        ReviewerToken.expires_at.is_not(None),
    )
    if activated_user_id is not None:
        stmt = stmt.where(ReviewerToken.activated_user_id == activated_user_id)
    rows = db.exec(stmt).all()

    changed = False
    affected_user_ids: set[int] = set()
    for token in rows:
        if not is_datetime_expired(token.expires_at, now=now_value):
            continue
        was_active = token.status == REVIEWER_TOKEN_STATUS_ACTIVE
        token.status = REVIEWER_TOKEN_STATUS_EXPIRED
        db.add(token)
        changed = True
        if was_active and token.activated_user_id:
            affected_user_ids.add(token.activated_user_id)

    if changed:
        for user_id in affected_user_ids:
            user = db.get(User, user_id)
            if not user:
                continue
            tokens = _query_active_tokens_for_user(db, user_id)
            user.is_reviewer = bool(tokens)
            user.reviewer_token_id = tokens[0].id if tokens else None
            user.updated_at = now_value
            db.add(user)
        if auto_commit:
            db.commit()
    return changed


def is_datetime_expired(value: datetime | None, *, now: datetime | None = None) -> bool:
    if value is None:
        return False
    now_value = _normalize_datetime(now or utcnow())
    return _normalize_datetime(value) < now_value


def _query_active_tokens_for_user(db: Session, user_id: int) -> list[ReviewerToken]:
    return db.exec(
        select(ReviewerToken)
        .where(
            ReviewerToken.activated_user_id == user_id,
            ReviewerToken.status == REVIEWER_TOKEN_STATUS_ACTIVE,
        )
        .order_by(ReviewerToken.created_at.desc())
    ).all()


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)

