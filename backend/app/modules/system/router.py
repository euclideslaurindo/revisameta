"""Health checks for the backend and its dependencies (10.5)."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import ServiceUnavailableError
from app.db.session import get_session
from app.integrations.stats_client import StatsClient, get_stats_client

logger = logging.getLogger(__name__)
router = APIRouter(tags=["system"])


class PublicConfig(BaseModel):
    """What the browser needs before login (no secrets)."""

    turnstile_enabled: bool
    turnstile_site_key: str
    terms_version: str
    pdf_max_size_mb: int


@router.get("/public-config")
async def public_config() -> PublicConfig:
    from app.modules.auth.service import TERMS_VERSION

    settings = get_settings()
    return PublicConfig(
        turnstile_enabled=settings.turnstile_enabled,
        turnstile_site_key=settings.turnstile_site_key if settings.turnstile_enabled else "",
        terms_version=TERMS_VERSION,
        pdf_max_size_mb=settings.pdf_max_size_mb,
    )


@router.get("/health/live")
async def live() -> dict[str, str]:
    """Process is up (used by the container healthcheck)."""
    return {"status": "ok"}


@router.get("/health")
async def health(
    response: Response,
    session: AsyncSession = Depends(get_session),
    stats: StatsClient = Depends(get_stats_client),
) -> dict[str, Any]:
    """Status of every dependency. Returns 503 if any of them is down."""
    checks: dict[str, Any] = {}

    try:
        await session.execute(text("SELECT 1"))
        checks["database"] = {"status": "ok"}
    except Exception as exc:  # pragma: no cover - exercised only when the DB is down
        logger.warning("health_database_failed", exc_info=exc)
        checks["database"] = {"status": "down"}

    redis = Redis.from_url(get_settings().redis_url)
    try:
        await redis.ping()
        checks["redis"] = {"status": "ok"}
    except Exception as exc:
        logger.warning("health_redis_failed", exc_info=exc)
        checks["redis"] = {"status": "down"}
    finally:
        await redis.aclose()

    try:
        stats_health = await stats.health()
        checks["stats_r"] = {
            "status": "ok" if stats_health.ok else "degraded",
            "r_version": stats_health.meta.r_version,
            "packages": stats_health.meta.packages,
            "robvis_commit": stats_health.meta.robvis_commit,
        }
    except ServiceUnavailableError:
        checks["stats_r"] = {"status": "down"}

    healthy = all(check["status"] == "ok" for check in checks.values())
    if not healthy:
        response.status_code = 503
    return {"status": "ok" if healthy else "degraded", "checks": checks}
