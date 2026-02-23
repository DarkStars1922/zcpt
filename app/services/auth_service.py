from datetime import datetime, timezone

from sqlalchemy import select
from sqlmodel import Session

from app.core.config import settings
from app.core.security import (
	TokenPayloadError,
	create_access_token,
	create_refresh_token,
	decode_token,
	hash_password,
	verify_password,
)
from app.models.refresh_token import RefreshToken
from app.models.user import User

VALID_ROLES = {"student", "teacher", "admin"}


class AuthError(Exception):
	def __init__(self, message: str, code: int = 1000):
		self.message = message
		self.code = code
		super().__init__(message)


def _ensure_utc_aware(value: datetime) -> datetime:
	if value.tzinfo is None:
		return value.replace(tzinfo=timezone.utc)
	return value.astimezone(timezone.utc)


def register_user(
	db: Session,
	*,
	account: str,
	password: str,
	name: str,
	role: str,
	class_id: int | None,
	is_auth: bool,
	email: str | None,
	phone: str | None,
) -> User:
	if role not in VALID_ROLES:
		raise AuthError("角色不合法", 1001)

	existing = db.scalar(select(User).where(User.account == account))
	if existing:
		raise AuthError("账号已存在", 1007)

	user = User(
		account=account,
		password_hash=hash_password(password),
		name=name,
		role=role,
		class_id=class_id,
		email=email,
		phone=phone,
		is_auth=is_auth,
	)
	db.add(user)
	db.commit()
	db.refresh(user)
	return user


def login_user(db: Session, *, account: str, password: str) -> tuple[User, str, str]:
	user = db.scalar(select(User).where(User.account == account))
	if not user or not verify_password(password, user.password_hash):
		raise AuthError("账号或密码错误", 1000)

	access_token = create_access_token(str(user.id), user.role)
	refresh_token = create_refresh_token(str(user.id))
	payload = decode_token(refresh_token)
	expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)

	record = RefreshToken(user_id=user.id, token_jti=payload["jti"], expires_at=expires_at)
	db.add(record)
	db.commit()
	return user, access_token, refresh_token


def refresh_access_token(db: Session, *, refresh_token: str) -> str:
	try:
		payload = decode_token(refresh_token)
	except TokenPayloadError as exc:
		raise AuthError(str(exc), 1006) from exc

	if payload.get("type") != "refresh":
		raise AuthError("refresh token 类型错误", 1006)

	token_record = db.scalar(select(RefreshToken).where(RefreshToken.token_jti == payload["jti"]))
	if not token_record or token_record.is_revoked:
		raise AuthError("refresh token 无效", 1006)
	if _ensure_utc_aware(token_record.expires_at) < datetime.now(timezone.utc):
		raise AuthError("refresh token 已过期", 1006)

	user = db.get(User, int(payload["sub"]))
	if not user:
		raise AuthError("用户不存在", 1002)

	return create_access_token(str(user.id), user.role)


def revoke_refresh_token(db: Session, *, refresh_token: str) -> None:
	try:
		payload = decode_token(refresh_token)
	except TokenPayloadError as exc:
		raise AuthError(str(exc), 1006) from exc

	token_record = db.scalar(select(RefreshToken).where(RefreshToken.token_jti == payload["jti"]))
	if not token_record:
		return

	token_record.is_revoked = True
	db.add(token_record)
	db.commit()


def get_current_user_by_access_token(db: Session, access_token: str) -> User:
	try:
		payload = decode_token(access_token)
	except TokenPayloadError as exc:
		raise AuthError(str(exc), 1005) from exc

	if payload.get("type") != "access":
		raise AuthError("access token 类型错误", 1005)

	user = db.get(User, int(payload["sub"]))
	if not user:
		raise AuthError("用户不存在", 1002)
	return user


def access_token_expire_seconds() -> int:
	return settings.access_token_expire_seconds
