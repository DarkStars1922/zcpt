import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any
import bcrypt
from jose import JWTError, jwt

from app.core.config import settings

MAX_BCRYPT_PASSWORD_BYTES = 72


class TokenPayloadError(Exception):
    pass


def validate_password_bytes_length(password: str) -> None:
    password_bytes = password.encode("utf-8")
    if len(password_bytes) > MAX_BCRYPT_PASSWORD_BYTES:
        raise ValueError(f"密码长度不能超过 {MAX_BCRYPT_PASSWORD_BYTES} 字节")


def hash_password(password: str) -> str:
    validate_password_bytes_length(password)
    password_bytes = password.encode("utf-8")
    hashed = bcrypt.hashpw(password_bytes, bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        validate_password_bytes_length(plain_password)
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except ValueError:
        return False


def _build_token(*, subject: str, token_type: str, expires_seconds: int, extra: dict[str, Any] | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expires_seconds)).timestamp()),
        "jti": str(uuid.uuid4()),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def create_access_token(subject: Annotated[str, "用户标识", "refresh_token"], role: Annotated[str, "用户身份"]) -> str:
    return _build_token(
        subject=subject,
        token_type="access",
        expires_seconds=settings.access_token_expire_seconds,
        extra={"role": role},
    )


def create_refresh_token(subject: Annotated[str, "用户标识", "refresh_token"]) -> str:
    return _build_token(subject=subject, token_type="refresh", expires_seconds=settings.refresh_token_expire_seconds)


def decode_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError as exc:
        raise TokenPayloadError("token 无效或已过期") from exc

    if "sub" not in payload or "type" not in payload or "jti" not in payload:
        raise TokenPayloadError("token 载荷不完整")
    return payload
