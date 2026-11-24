"""AI on/off per project with the data-use notice (docs/ia.md 7.15.5; stage 7 step 2).

- Off by default; only an admin turns it on, and only by accepting the current notice.
- If the notice changes, an earlier acceptance no longer counts: the AI is treated as
  off until someone accepts the new version.
- `require(ctx, function)` is what every AI feature calls first: it refuses when the AI
  is off, the function is not allowed, it was switched off for low accuracy, or no
  provider is configured on the server. A refused call never reaches the provider.
"""

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError, ConflictError, ForbiddenError
from app.modules.ai.models import AISettings
from app.modules.ai.notice import NOTICE, VERSION
from app.modules.auth.models import User
from app.modules.projects.access import ProjectContext

Function = Literal["tutor", "locate", "extract", "rob", "search", "draft"]
FUNCTIONS: list[str] = ["tutor", "locate", "extract", "rob", "search", "draft"]


class AISettingsOut(BaseModel):
    enabled: bool
    functions: list[str]
    disabled_functions: dict[str, str]
    provider: str
    server_configured: bool  # a provider and key exist on this server
    notice_version: str  # current version of the notice
    accepted_version: str | None
    accepted_by_name: str | None
    accepted_at: datetime | None
    notice: dict[str, Any]
    version: int | None


def _all_functions() -> list[Function]:
    return ["tutor", "locate", "extract", "rob", "search", "draft"]


class AISettingsIn(BaseModel):
    enabled: bool
    functions: list[Function] = Field(default_factory=_all_functions)
    accept_notice_version: str | None = None  # needed to turn it on
    version: int | None = None


async def _row(session: AsyncSession, ctx: ProjectContext) -> AISettings | None:
    return (
        await session.scalars(select(AISettings).where(AISettings.project_id == ctx.project.id))
    ).first()


def _active(row: AISettings | None) -> bool:
    return bool(row and row.enabled and row.notice_version == VERSION)


async def get(session: AsyncSession, ctx: ProjectContext) -> AISettingsOut:
    row = await _row(session, ctx)
    settings = get_settings()
    name = None
    if row and row.accepted_by:
        name = await session.scalar(select(User.name).where(User.id == row.accepted_by))
    return AISettingsOut(
        enabled=_active(row),
        functions=list(row.functions) if row else list(FUNCTIONS),
        disabled_functions=dict(row.disabled_functions or {}) if row else {},
        provider=settings.ai_provider,
        server_configured=settings.ai_provider != "none"
        and (settings.ai_provider != "gemini" or bool(settings.gemini_api_key)),
        notice_version=VERSION,
        accepted_version=row.notice_version if row else None,
        accepted_by_name=name,
        accepted_at=row.accepted_at if row else None,
        notice=NOTICE,
        version=row.version if row else None,
    )


async def update(session: AsyncSession, ctx: ProjectContext, data: AISettingsIn) -> AISettingsOut:
    if not ctx.is_admin:
        raise ForbiddenError()
    row = await _row(session, ctx)
    if row is not None and data.version != row.version:
        raise ConflictError()
    if row is None and data.version is not None:
        raise ConflictError()
    if row is None:
        row = AISettings(
            project_id=ctx.project.id,
            enabled=False,
            provider=get_settings().ai_provider,
            functions=list(FUNCTIONS),
            disabled_functions={},
            created_by=ctx.user.id,
        )
        session.add(row)
    if data.enabled and not _active(row):
        # Turning on (or keeping on after a new notice) needs the current notice accepted.
        if data.accept_notice_version != VERSION:
            raise AppError("ai.notice_required", status_code=422)
        row.notice_version = VERSION
        row.accepted_by = ctx.user.id
        row.accepted_at = datetime.now(UTC)
    row.enabled = data.enabled
    row.functions = list(dict.fromkeys(data.functions))
    row.provider = get_settings().ai_provider
    if data.enabled:
        # Turning a function back on by hand clears its low-accuracy switch-off.
        row.disabled_functions = {
            k: v for k, v in (row.disabled_functions or {}).items() if k not in data.functions
        }
    await session.commit()
    return await get(session, ctx)


async def require(session: AsyncSession, ctx: ProjectContext, function: str) -> AISettings:
    row = await _row(session, ctx)
    if not _active(row) or row is None:
        raise AppError("ai.disabled", status_code=409)
    if function not in (row.functions or []):
        raise AppError("ai.function_disabled", status_code=409)
    if function in (row.disabled_functions or {}):
        raise AppError("ai.low_accuracy", status_code=409)
    settings = get_settings()
    if settings.ai_provider == "none" or (
        settings.ai_provider == "gemini" and not settings.gemini_api_key
    ):
        raise AppError("ai.unavailable", status_code=503)
    return row


def project_id_of(row: AISettings) -> uuid.UUID:
    return row.project_id
