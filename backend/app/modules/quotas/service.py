"""Quotas protect the free server from a single user filling it (docs/dominio.md, 6)."""

import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import QuotaExceededError
from app.modules.projects.models import Project
from app.modules.quotas.models import UsageQuota


class QuotaKind(enum.StrEnum):
    PROJECTS = "projects"
    STORAGE_MB = "storage_mb"
    AI_CALLS = "ai_calls"  # per day


def default_limit(kind: QuotaKind) -> int:
    settings = get_settings()
    return {
        QuotaKind.PROJECTS: settings.quota_projects_per_user,
        QuotaKind.STORAGE_MB: settings.quota_storage_mb_per_user,
        QuotaKind.AI_CALLS: settings.ai_calls_per_user_day,
    }[kind]


async def _override(
    session: AsyncSession, user_id: uuid.UUID, kind: QuotaKind
) -> UsageQuota | None:
    return (
        await session.scalars(
            select(UsageQuota).where(
                UsageQuota.user_id == user_id,
                UsageQuota.kind == kind.value,
                UsageQuota.period == "total",
            )
        )
    ).first()


async def get_limit(session: AsyncSession, user_id: uuid.UUID, kind: QuotaKind) -> int:
    row = await _override(session, user_id, kind)
    if row is not None and row.limit_value is not None:
        return row.limit_value
    return default_limit(kind)


async def set_limit(
    session: AsyncSession, user_id: uuid.UUID, kind: QuotaKind, limit: int | None
) -> None:
    row = await _override(session, user_id, kind)
    if row is None:
        row = UsageQuota(user_id=user_id, kind=kind.value, period="total", used=0)
        session.add(row)
    row.limit_value = limit
    await session.commit()


async def projects_used(session: AsyncSession, user_id: uuid.UUID) -> int:
    count = await session.scalar(
        select(func.count()).select_from(Project).where(Project.owner_id == user_id)
    )
    return int(count or 0)


async def storage_used_mb(session: AsyncSession, user_id: uuid.UUID) -> float:
    """Filled in by the uploads module; 0 until files exist."""
    from app.modules.uploads.service import storage_used_bytes

    return round(await storage_used_bytes(session, user_id) / (1024 * 1024), 2)


async def ensure_can_create_project(session: AsyncSession, user_id: uuid.UUID) -> None:
    limit = await get_limit(session, user_id, QuotaKind.PROJECTS)
    if await projects_used(session, user_id) >= limit:
        raise QuotaExceededError("quota.projects_exceeded", limit=limit)


async def ensure_storage_available(
    session: AsyncSession, user_id: uuid.UUID, extra_bytes: int
) -> None:
    limit_mb = await get_limit(session, user_id, QuotaKind.STORAGE_MB)
    used = await storage_used_mb(session, user_id)
    if used + extra_bytes / (1024 * 1024) > limit_mb:
        raise QuotaExceededError("quota.storage_exceeded", limit=limit_mb)


def _today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


async def _ai_row(session: AsyncSession, user_id: uuid.UUID) -> UsageQuota | None:
    return (
        await session.scalars(
            select(UsageQuota).where(
                UsageQuota.user_id == user_id,
                UsageQuota.kind == QuotaKind.AI_CALLS.value,
                UsageQuota.period == _today(),
            )
        )
    ).first()


async def ai_calls_used(session: AsyncSession, user_id: uuid.UUID) -> int:
    row = await _ai_row(session, user_id)
    return int(row.used) if row else 0


async def ai_calls_left(session: AsyncSession, user_id: uuid.UUID) -> int:
    limit = await get_limit(session, user_id, QuotaKind.AI_CALLS)
    return limit - await ai_calls_used(session, user_id)


async def count_ai_call(session: AsyncSession, user_id: uuid.UUID) -> None:
    """One more AI call today (UTC). The caller commits."""
    row = await _ai_row(session, user_id)
    if row is None:
        row = UsageQuota(user_id=user_id, kind=QuotaKind.AI_CALLS.value, period=_today(), used=0)
        session.add(row)
    row.used = int(row.used) + 1
    await session.flush()


async def usage(session: AsyncSession, user_id: uuid.UUID) -> dict[str, dict[str, float]]:
    return {
        QuotaKind.PROJECTS.value: {
            "used": await projects_used(session, user_id),
            "limit": await get_limit(session, user_id, QuotaKind.PROJECTS),
        },
        QuotaKind.STORAGE_MB.value: {
            "used": await storage_used_mb(session, user_id),
            "limit": await get_limit(session, user_id, QuotaKind.STORAGE_MB),
        },
        QuotaKind.AI_CALLS.value: {
            "used": await ai_calls_used(session, user_id),
            "limit": await get_limit(session, user_id, QuotaKind.AI_CALLS),
        },
    }
