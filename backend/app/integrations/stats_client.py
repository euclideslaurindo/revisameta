"""Client for the R statistics service (docs/estatistica.md, 8.2).

The backend never computes statistics; it sends data to R and receives results.
Timeouts and retries are applied here; when R is down, callers get a clear
ServiceUnavailableError and nothing is saved as a result.
"""

import asyncio
import logging
from typing import Any

import httpx
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.errors import ServiceUnavailableError
from app.core.logging import REQUEST_ID_HEADER, request_id_var

logger = logging.getLogger(__name__)

RETRIES = 2
BACKOFF_SECONDS = 0.5


class StatsMeta(BaseModel):
    r_version: str
    packages: dict[str, str | None]
    robvis_commit: str | None = None
    params: dict[str, Any] | list[Any] = Field(default_factory=dict)


class StatsResponse(BaseModel):
    ok: bool
    result: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    meta: StatsMeta


class StatsClient:
    def __init__(
        self,
        base_url: str | None = None,
        timeout: float | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        settings = get_settings()
        self._base_url = base_url or settings.stats_r_url
        self._timeout = timeout or settings.stats_r_timeout_seconds
        self._transport = transport

    def _headers(self) -> dict[str, str]:
        request_id = request_id_var.get()
        return {REQUEST_ID_HEADER: request_id} if request_id else {}

    async def _request(self, method: str, path: str, json: Any = None) -> StatsResponse:
        last_error: Exception | None = None
        async with httpx.AsyncClient(
            base_url=self._base_url, timeout=self._timeout, transport=self._transport
        ) as client:
            for attempt in range(RETRIES + 1):
                try:
                    response = await client.request(
                        method, path, json=json, headers=self._headers()
                    )
                    if response.status_code >= 500 and response.status_code != 503:
                        response.raise_for_status()
                    return StatsResponse.model_validate(response.json())
                except (httpx.TransportError, httpx.HTTPStatusError, ValueError) as exc:
                    last_error = exc
                    logger.warning(
                        "stats_r_request_failed",
                        extra={
                            "extra_fields": {
                                "path": path,
                                "attempt": attempt + 1,
                                "error": str(exc),
                            }
                        },
                    )
                    if attempt < RETRIES:
                        await asyncio.sleep(BACKOFF_SECONDS * (2**attempt))
        raise ServiceUnavailableError() from last_error

    async def health(self) -> StatsResponse:
        return await self._request("GET", "/health")

    async def kappa(self, rater_a: list[str], rater_b: list[str]) -> StatsResponse:
        """% of equal codes and Cohen's kappa between two raters (irr, in R)."""
        return await self._request("POST", "/kappa", json={"rater_a": rater_a, "rater_b": rater_b})


def get_stats_client() -> StatsClient:
    return StatsClient()
