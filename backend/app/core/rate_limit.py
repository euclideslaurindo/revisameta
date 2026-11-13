"""Rate limiting (login, registration) backed by Redis, plus failed-login tracking."""

from redis.asyncio import Redis
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import get_settings

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=get_settings().redis_url,
    strategy="fixed-window",
    headers_enabled=False,
)

FAILED_LOGIN_WINDOW_SECONDS = 15 * 60
CAPTCHA_AFTER_FAILURES = 3


def _redis() -> Redis:
    client: Redis = Redis.from_url(get_settings().redis_url)
    return client


def _key(email: str) -> str:
    return f"login-failures:{email.lower()}"


async def failed_logins(email: str) -> int:
    async with _redis() as redis:
        value = await redis.get(_key(email))
    return int(value or 0)


async def register_failed_login(email: str) -> None:
    async with _redis() as redis:
        key = _key(email)
        await redis.incr(key)
        await redis.expire(key, FAILED_LOGIN_WINDOW_SECONDS)


async def clear_failed_logins(email: str) -> None:
    async with _redis() as redis:
        await redis.delete(_key(email))
