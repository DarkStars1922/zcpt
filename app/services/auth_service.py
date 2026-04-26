from datetime import datetime, timezone

from sqlmodel import Session, select

from app.core.cache import blacklist_access_token, is_access_token_blacklisted
from app.core.config import settings
from app.core.constants import ROLE_STUDENT, REVIEWER_TOKEN_STATUS_ACTIVE
from app.core.security import (
    TokenPayloadError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    seconds_until_timestamp,
    verify_password,
)
from app.core.utils import ensure_utc_datetime, utcnow
from app.models.refresh_token import RefreshToken
from app.models.reviewer_token import ReviewerToken
from app.models.user import User
from app.schemas.auth import ChangePasswordRequest
from app.services.class_service import get_class_info, is_graduating_class
from app.services.errors import ServiceError
from app.services.reviewer_scope_service import (
    is_datetime_expired,
    refresh_user_reviewer_state,
    sync_reviewer_token_expirations,
)
from app.services.serializers import serialize_user
from app.services.system_log_service import write_system_log


def register_user(
    db: Session,
    *,
    account: str,
    password: str,
    name: str,
    role: str,
    class_id: int | None,
    is_reviewer: bool | None,
    reviewer_token: str | None,
    email: str | None,
    phone: str | None,
) -> User:
    if role != ROLE_STUDENT:
        raise ServiceError("公开注册仅支持学生账号，教师账号请由管理员创建", 1003)
    if class_id is None:
        raise ServiceError("学生注册必须选择班级", 1001)
    if not get_class_info(db, class_id, active_only=True) or is_graduating_class(db, class_id):
        raise ServiceError("请选择有效班级", 1001)
    if is_reviewer and not (reviewer_token or "").strip():
        raise ServiceError("申请审核员身份必须填写老师分配的激活码", 1001)

    existing = db.exec(select(User).where(User.account == account)).first()
    if existing:
        raise ServiceError("账号已存在", 1007)

    token_record = _validate_reviewer_token_for_register(db, reviewer_token) if is_reviewer else None

    user = User(
        account=account,
        password_hash=hash_password(password),
        name=name,
        role=ROLE_STUDENT,
        class_id=class_id,
        is_reviewer=False,
        email=email,
        phone=phone,
        updated_at=utcnow(),
    )
    db.add(user)
    db.flush()
    if token_record:
        token_record.status = REVIEWER_TOKEN_STATUS_ACTIVE
        token_record.activated_user_id = user.id
        token_record.activated_at = utcnow()
        token_record.revoked_at = None
        db.add(token_record)
        refresh_user_reviewer_state(db, user)
    db.commit()
    db.refresh(user)
    write_system_log(db, action="auth.register", actor_id=user.id, target_type="user", target_id=str(user.id))
    return user


def login_user(db: Session, *, account: str, password: str) -> tuple[dict, str, str]:
    user = db.exec(select(User).where(User.account == account, User.is_deleted.is_(False))).first()
    if not user or not verify_password(password, user.password_hash):
        raise ServiceError("账号或密码错误", 1000)

    access_token = create_access_token(str(user.id), user.role)
    refresh_token = create_refresh_token(str(user.id))
    payload = decode_token(refresh_token)
    record = RefreshToken(
        user_id=user.id,
        token_jti=payload["jti"],
        expires_at=datetime.fromtimestamp(payload["exp"], tz=timezone.utc),
        updated_at=utcnow(),
    )
    db.add(record)
    db.commit()
    write_system_log(db, action="auth.login", actor_id=user.id, target_type="user", target_id=str(user.id))
    return serialize_user(user), access_token, refresh_token


def refresh_access_token(db: Session, *, refresh_token: str) -> str:
    payload = _decode_refresh_token(refresh_token)
    token_record = db.exec(select(RefreshToken).where(RefreshToken.token_jti == payload["jti"])).first()
    if not token_record or token_record.is_revoked:
        raise ServiceError("refresh token 无效", 1006)
    expires_at = ensure_utc_datetime(token_record.expires_at)
    if expires_at is None:
        raise ServiceError("refresh token 无效", 1006)
    if expires_at < utcnow():
        raise ServiceError("refresh token 已过期", 1006)

    user = db.get(User, int(payload["sub"]))
    if not user or user.is_deleted:
        raise ServiceError("用户不存在", 1002)
    return create_access_token(str(user.id), user.role)


def revoke_refresh_token(db: Session, *, refresh_token: str) -> None:
    payload = _decode_refresh_token(refresh_token)
    token_record = db.exec(select(RefreshToken).where(RefreshToken.token_jti == payload["jti"])).first()
    if not token_record:
        return
    token_record.is_revoked = True
    token_record.updated_at = utcnow()
    db.add(token_record)
    db.commit()


def revoke_all_refresh_tokens_for_user(db: Session, *, user_id: int) -> None:
    rows = db.exec(select(RefreshToken).where(RefreshToken.user_id == user_id, RefreshToken.is_revoked.is_(False))).all()
    now = utcnow()
    for row in rows:
        row.is_revoked = True
        row.updated_at = now
        db.add(row)
    db.commit()


def logout_user(db: Session, *, access_token: str, refresh_token: str) -> None:
    user, access_payload = get_current_user_by_access_token(db, access_token, with_payload=True)
    revoke_refresh_token(db, refresh_token=refresh_token)
    blacklist_access_token(access_payload["jti"], seconds_until_timestamp(access_payload["exp"]))
    write_system_log(db, action="auth.logout", actor_id=user.id, target_type="user", target_id=str(user.id))


def change_password(db: Session, *, user: User, access_token: str, payload: ChangePasswordRequest) -> None:
    if not verify_password(payload.old_password, user.password_hash):
        raise ServiceError("旧密码错误", 1000)
    user.password_hash = hash_password(payload.new_password)
    user.updated_at = utcnow()
    db.add(user)
    db.commit()
    revoke_all_refresh_tokens_for_user(db, user_id=user.id)
    access_payload = decode_token(access_token)
    blacklist_access_token(access_payload["jti"], seconds_until_timestamp(access_payload["exp"]))
    write_system_log(db, action="auth.change_password", actor_id=user.id, target_type="user", target_id=str(user.id))


def get_current_user_by_access_token(
    db: Session,
    access_token: str,
    *,
    with_payload: bool = False,
) -> User | tuple[User, dict]:
    try:
        payload = decode_token(access_token)
    except TokenPayloadError as exc:
        raise ServiceError(str(exc), 1005) from exc

    if payload.get("type") != "access":
        raise ServiceError("access token 类型错误", 1005)
    if is_access_token_blacklisted(payload["jti"]):
        raise ServiceError("access token 已失效", 1005)

    user = db.get(User, int(payload["sub"]))
    if not user:
        raise ServiceError("用户不存在", 1002)
    if with_payload:
        return user, payload
    return user


def access_token_expire_seconds() -> int:
    return settings.access_token_expire_seconds


def _validate_reviewer_token_for_register(db: Session, token_value: str | None) -> ReviewerToken:
    token_text = (token_value or "").strip()
    sync_reviewer_token_expirations(db, auto_commit=False)
    token = db.exec(select(ReviewerToken).where(ReviewerToken.token == token_text)).first()
    if not token:
        raise ServiceError("审核员激活码不存在", 1002)
    if token.status == "revoked":
        raise ServiceError("审核员激活码已撤销", 1000)
    if is_datetime_expired(token.expires_at):
        token.status = "expired"
        db.add(token)
        raise ServiceError("审核员激活码已过期", 1000)
    if token.status == REVIEWER_TOKEN_STATUS_ACTIVE and token.activated_user_id:
        raise ServiceError("审核员激活码已被使用", 1007)
    return token


def _decode_refresh_token(refresh_token: str) -> dict:
    try:
        payload = decode_token(refresh_token)
    except TokenPayloadError as exc:
        raise ServiceError(str(exc), 1006) from exc
    if payload.get("type") != "refresh":
        raise ServiceError("refresh token 类型错误", 1006)
    return payload
