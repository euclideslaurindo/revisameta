"""arq worker: `arq app.workers.main.WorkerSettings` (ADR-005)."""

import uuid
from typing import Any, ClassVar

from arq import cron

from app.core.logging import configure_logging
from app.db import models as _models  # noqa: F401 - register mappers
from app.db.session import dispose_engine, get_sessionmaker
from app.integrations.queue import redis_settings
from app.integrations.storage import Storage
from app.modules.references.service import process_search
from app.modules.uploads.processing import process_upload
from app.modules.uploads.service import expire_stale_uploads


async def process_upload_task(_ctx: dict[str, Any], upload_id: str, job_id: str) -> None:
    await process_upload(get_sessionmaker(), Storage(), uuid.UUID(upload_id), uuid.UUID(job_id))


async def import_search_task(_ctx: dict[str, Any], search_id: str, job_id: str) -> None:
    await process_search(get_sessionmaker(), Storage(), uuid.UUID(search_id), uuid.UUID(job_id))


async def expire_uploads_task(_ctx: dict[str, Any]) -> int:
    async with get_sessionmaker()() as session:
        return await expire_stale_uploads(session, Storage())


async def startup(_ctx: dict[str, Any]) -> None:
    configure_logging()


async def shutdown(_ctx: dict[str, Any]) -> None:
    await dispose_engine()


class WorkerSettings:
    functions: ClassVar[list[Any]] = [process_upload_task, import_search_task]
    cron_jobs: ClassVar[list[Any]] = [
        cron(expire_uploads_task, minute={0, 30})  # type: ignore[arg-type]
    ]
    redis_settings = redis_settings()
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = 4
    job_timeout = 30 * 60
