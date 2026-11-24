"""The only way the system calls an AI provider (docs/ia.md 7.15.5; stage 7 step 3).

In this order, for every call:
1. `settings.require`: the AI is on in the project, the function is allowed and a
   provider exists. Otherwise nothing is sent.
2. Cache by (project, function, prompt version, model, instructions, content): the same
   question never spends quota twice, and no project reads another project's answers.
3. Quota of the person for the day (default 30 calls; per-user override in
   usage_quotas), then the global limits shared by every process through Redis: calls
   per minute and calls per day (the free quota belongs to one Google project and
   resets at midnight Pacific time, so the daily window follows that clock).
4. The provider. A 429 or our own limits become `ai.quota_exceeded`, a normal state:
   the feature is unavailable until it renews, the rest of the system keeps working.
Only structured answers validated by a schema come out of here.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError
from app.integrations.ai import AIProvider
from app.integrations.ai.base import (
    AIError,
    AIInvalidOutputError,
    AIQuotaExceededError,
    AIUnavailableError,
)
from app.modules.ai import settings as ai_settings
from app.modules.ai.models import AICacheEntry
from app.modules.projects.access import ProjectContext
from app.modules.quotas.service import ai_calls_left, count_ai_call

PACIFIC = ZoneInfo("America/Los_Angeles")


@dataclass
class CallResult[T: BaseModel]:
    answer: T
    cached: bool
    model: str
    provider: str


def cache_key(
    project_id: str, function: str, prompt_version: str, model: str, system: str, prompt: str
) -> str:
    raw = json.dumps(
        [project_id, function, prompt_version, model, system, prompt], ensure_ascii=False
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def _redis() -> Redis:
    client: Redis = Redis.from_url(get_settings().redis_url)
    return client


async def _take_global_slot(now: datetime | None = None) -> None:
    """Counts the call in the shared per-minute and per-day windows; refuses when full."""
    settings = get_settings()
    now = now or datetime.now(UTC)
    minute = f"ai:minute:{now.strftime('%Y%m%d%H%M')}"
    day = f"ai:day:{now.astimezone(PACIFIC).strftime('%Y%m%d')}"
    async with _redis() as redis:
        pipe = redis.pipeline()
        pipe.incr(minute)
        pipe.expire(minute, 120)
        pipe.incr(day)
        pipe.expire(day, 2 * 86400)
        per_minute, _, per_day, _ = await pipe.execute()
        if per_minute > settings.ai_calls_per_minute or per_day > settings.ai_calls_per_day:
            # Give the slot back: a refused call must not use up the window.
            await redis.decr(minute)
            await redis.decr(day)
            raise AppError("ai.quota_exceeded", status_code=429)


def _app_error(error: AIError) -> AppError:
    if isinstance(error, AIQuotaExceededError):
        return AppError("ai.quota_exceeded", status_code=429)
    if isinstance(error, AIUnavailableError):
        return AppError("ai.unavailable", status_code=503)
    if isinstance(error, AIInvalidOutputError):
        return AppError("ai.invalid_output", status_code=502)
    return AppError("ai.failed", status_code=502)


async def call[T: BaseModel](
    session: AsyncSession,
    ctx: ProjectContext,
    provider: AIProvider,
    *,
    function: str,
    prompt_version: str,
    system: str,
    prompt: str,
    schema: type[T],
) -> CallResult[T]:
    await ai_settings.require(session, ctx, function)
    key = cache_key(str(ctx.project.id), function, prompt_version, provider.model, system, prompt)
    hit = (
        await session.scalars(
            select(AICacheEntry).where(
                AICacheEntry.project_id == ctx.project.id, AICacheEntry.key == key
            )
        )
    ).first()
    if hit is not None:
        try:
            return CallResult(schema.model_validate(hit.answer), True, hit.model, hit.provider)
        except ValueError:
            pass  # schema changed: ask again
    if await ai_calls_left(session, ctx.user.id) <= 0:
        raise AppError("ai.quota_exceeded", status_code=429)
    await _take_global_slot()
    try:
        answer = await provider.complete_structured(system, prompt, schema)
    except AIInvalidOutputError as error:
        await count_ai_call(session, ctx.user.id)  # the provider was used
        await session.commit()
        raise _app_error(error) from error
    except AIError as error:
        raise _app_error(error) from error
    await count_ai_call(session, ctx.user.id)
    stored: dict[str, Any] = answer.model_dump(mode="json")
    if hit is None:
        session.add(
            AICacheEntry(
                project_id=ctx.project.id,
                key=key,
                function=function,
                prompt_version=prompt_version,
                model=provider.model,
                provider=provider.name,
                answer=stored,
            )
        )
    else:
        hit.answer = stored
    await session.commit()
    return CallResult(answer, False, provider.model, provider.name)
