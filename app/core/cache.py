import json
import time
from typing import Any

from redis import Redis
from redis.exceptions import RedisError

from app.core.config import settings

_redis_client: Redis | None = None
_memory_store: dict[str, tuple[str, float | None]] = {}


def get_redis() -> Redis | None:
    global _redis_client
    if not settings.redis_enabled:
        return None
    if _redis_client is None:
        try:
            _redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
            _redis_client.ping()
        except RedisError:
            _redis_client = None
    return _redis_client


def set_json(key: str, value: Any, ttl_seconds: int | None = None) -> bool:
    payload = json.dumps(value, ensure_ascii=False)
    client = get_redis()
    if client is None:
        _memory_set(key, payload, ttl_seconds)
        return True
    try:
        client.set(name=key, value=payload, ex=ttl_seconds)
        return True
    except RedisError:
        _memory_set(key, payload, ttl_seconds)
        return True


def get_json(key: str) -> Any | None:
    client = get_redis()
    payload: str | None
    if client is None:
        payload = _memory_get(key)
    else:
        try:
            payload = client.get(name=key)
        except RedisError:
            payload = _memory_get(key)
    if not payload:
        return None
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return None


def delete_key(key: str) -> None:
    client = get_redis()
    if client is None:
        _memory_delete(key)
        return
    try:
        client.delete(key)
    except RedisError:
        _memory_delete(key)


def build_blacklist_key(jti: str) -> str:
    return f"{settings.access_token_blacklist_prefix}{jti}"


def blacklist_access_token(jti: str, ttl_seconds: int) -> bool:
    key = build_blacklist_key(jti)
    client = get_redis()
    if client is None:
        _memory_set(key, "1", max(ttl_seconds, 1))
        return True
    try:
        client.set(name=key, value="1", ex=max(ttl_seconds, 1))
        return True
    except RedisError:
        _memory_set(key, "1", max(ttl_seconds, 1))
        return True


def is_access_token_blacklisted(jti: str) -> bool:
    key = build_blacklist_key(jti)
    client = get_redis()
    if client is None:
        return _memory_get(key) is not None
    try:
        return bool(client.exists(key))
    except RedisError:
        return _memory_get(key) is not None


def build_idempotency_key(scope: str, key: str) -> str:
    return f"{settings.idempotency_prefix}{scope}:{key}"


def _memory_set(key: str, value: str, ttl_seconds: int | None) -> None:
    expires_at = time.time() + ttl_seconds if ttl_seconds else None
    _memory_store[key] = (value, expires_at)


def _memory_get(key: str) -> str | None:
    payload = _memory_store.get(key)
    if payload is None:
        return None
    value, expires_at = payload
    if expires_at is not None and expires_at <= time.time():
        _memory_store.pop(key, None)
        return None
    return value


def _memory_delete(key: str) -> None:
    _memory_store.pop(key, None)
