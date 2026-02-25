import secrets
from datetime import datetime, timezone

from sqlalchemy import and_, select
from sqlmodel import Session

from app.models.reviewer_token import ReviewerToken
from app.models.user import User


class TokenError(Exception):
    def __init__(self, message: str, code: int = 1000):
        self.message = message
        self.code = code
        super().__init__(message)


def _ensure_utc_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _ensure_manager_role(user: User) -> None:
    if user.role not in {"teacher", "admin"}:
        raise TokenError("无权限", 1003)


def _ensure_student_role(user: User) -> None:
    if user.role != "student":
        raise TokenError("无权限", 1003)


def _calc_status(token: ReviewerToken, now: datetime) -> str:
    if token.is_revoked:
        return "revoked"
    if _ensure_utc_aware(token.expired_at) < now:
        return "expired"
    return "active"


def _serialize(token: ReviewerToken, now: datetime) -> dict:
    return {
        "id": token.id,
        "token": token.token,
        "type": token.token_type,
        "class_ids": token.class_ids,
        "status": _calc_status(token, now),
        "expired_at": _ensure_utc_aware(token.expired_at).isoformat(),
        "created_at": _ensure_utc_aware(token.created_at).isoformat(),
        "activated_at": _ensure_utc_aware(token.activated_at).isoformat() if token.activated_at else None,
        "activated_user_id": token.activated_user_id,
    }


def _clear_user_reviewer_binding(db: Session, token: ReviewerToken) -> None:
    if token.activated_user_id is None:
        return

    user = db.get(User, token.activated_user_id)
    if user is None:
        return

    if user.reviewer_token_id == token.id:
        user.is_reviewer = False
        user.reviewer_token_id = None
        db.add(user)


def _cleanup_expired_token_bindings(db: Session) -> None:
    now = datetime.now(timezone.utc)
    expired_rows = db.scalars(
        select(ReviewerToken).where(
            ReviewerToken.activated_user_id.is_not(None),
            ReviewerToken.is_revoked.is_(False),
            ReviewerToken.expired_at < now,
        )
    ).all()
    if not expired_rows:
        return

    for row in expired_rows:
        _clear_user_reviewer_binding(db, row)
        row.activated_user_id = None
        row.activated_at = None
        db.add(row)

    db.commit()


def _generate_reviewer_token() -> str:
    return f"rvw_{secrets.token_urlsafe(12).replace('-', '').replace('_', '')[:16]}"


def create_reviewer_token(db: Session, user: User, *, class_ids: list[int], expired_at: datetime) -> ReviewerToken:
    _ensure_manager_role(user)

    normalized_expired_at = _ensure_utc_aware(expired_at)
    now = datetime.now(timezone.utc)
    if normalized_expired_at <= now:
        raise TokenError("过期时间必须大于当前时间", 1001)

    token_value = _generate_reviewer_token()
    while db.scalar(select(ReviewerToken).where(ReviewerToken.token == token_value)) is not None:
        token_value = _generate_reviewer_token()

    row = ReviewerToken(
        token=token_value,
        token_type="reviewer",
        creator_user_id=user.id,
        expired_at=normalized_expired_at,
    )
    row.set_class_ids(class_ids)

    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def activate_reviewer_token(db: Session, user: User, *, token: str) -> ReviewerToken:
    _ensure_student_role(user)

    row = db.scalar(select(ReviewerToken).where(ReviewerToken.token == token))
    if not row:
        raise TokenError("资源不存在", 1002)

    now = datetime.now(timezone.utc)
    if row.is_revoked:
        raise TokenError("令牌已失效", 1000)
    if _ensure_utc_aware(row.expired_at) < now:
        raise TokenError("令牌已过期", 1000)
    if row.activated_user_id is not None and row.activated_user_id != user.id:
        raise TokenError("令牌已被绑定", 1007)

    previous_bound = db.scalar(
        select(ReviewerToken).where(ReviewerToken.activated_user_id == user.id, ReviewerToken.id != row.id)
    )
    if previous_bound:
        previous_bound.activated_user_id = None
        previous_bound.activated_at = None
        db.add(previous_bound)

    row.activated_user_id = user.id
    row.activated_at = now
    user.is_reviewer = True
    user.reviewer_token_id = row.id

    db.add(row)
    db.add(user)
    db.commit()
    db.refresh(row)
    return row


def list_tokens(
    db: Session,
    user: User,
    *,
    token_type: str,
    status: str | None,
    page: int,
    size: int,
) -> dict:
    _ensure_manager_role(user)
    _cleanup_expired_token_bindings(db)

    if token_type not in {"reviewer"}:
        raise TokenError("type 参数不合法", 1001)

    conditions = [ReviewerToken.token_type == token_type]
    stmt = select(ReviewerToken).where(and_(*conditions)).order_by(ReviewerToken.created_at.desc())
    rows = db.scalars(stmt).all()

    now = datetime.now(timezone.utc)
    if status:
        if status not in {"active", "expired", "revoked"}:
            raise TokenError("status 参数不合法", 1001)
        rows = [row for row in rows if _calc_status(row, now) == status]

    total = len(rows)
    start = (page - 1) * size
    end = start + size
    paged_rows = rows[start:end]

    return {
        "page": page,
        "size": size,
        "total": total,
        "list": [_serialize(row, now) for row in paged_rows],
    }


def revoke_token(db: Session, user: User, *, token_id: int) -> ReviewerToken:
    _ensure_manager_role(user)

    row = db.get(ReviewerToken, token_id)
    if not row:
        raise TokenError("资源不存在", 1002)

    if row.is_revoked:
        return row

    row.is_revoked = True
    _clear_user_reviewer_binding(db, row)
    row.activated_user_id = None
    row.activated_at = None
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
