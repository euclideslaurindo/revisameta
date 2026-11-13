"""Background job queue (arq + Redis, ADR-005)."""

from typing import Any, Protocol

from arq import ArqRedis, create_pool
from arq.connections import RedisSettings

from app.core.config import get_settings


class JobQueue(Protocol):
    async def enqueue(self, function: str, **kwargs: Any) -> None: ...


def redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(get_settings().redis_url)


class ArqQueue:
    def __init__(self) -> None:
        self._pool: ArqRedis | None = None

    async def enqueue(self, function: str, **kwargs: Any) -> None:
        if self._pool is None:
            self._pool = await create_pool(redis_settings())
        await self._pool.enqueue_job(function, **kwargs)


_queue = ArqQueue()


def get_job_queue() -> JobQueue:
    return _queue
