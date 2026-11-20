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

    async def effect_sizes(self, spec: dict[str, Any]) -> StatsResponse:
        """Effect and variance of each study (metafor::escalc)."""
        return await self._request("POST", "/effect-sizes", json=spec)

    async def meta_analysis(self, spec: dict[str, Any]) -> StatsResponse:
        """Pooled effect, heterogeneity and prediction interval (metafor::rma + predict)."""
        return await self._request("POST", "/meta-analysis", json=spec)

    async def convert(self, conversions: list[dict[str, Any]]) -> StatsResponse:
        """Data conversions (8.5); each item reports its method and whether it is estimated."""
        return await self._request("POST", "/convert", json={"conversions": conversions})

    async def combine_groups(self, spec: dict[str, Any]) -> StatsResponse:
        """Several arms into one group (Cochrane Handbook formula)."""
        return await self._request("POST", "/combine-groups", json=spec)

    async def forest_plot(self, spec: dict[str, Any]) -> StatsResponse:
        """Forest plot with weights, pooled effect and prediction interval."""
        return await self._request("POST", "/forest-plot", json=spec)

    async def plausibility_checks(self, spec: dict[str, Any]) -> StatsResponse:
        """SD that looks like an SE, reported p that does not match the data (warnings)."""
        return await self._request("POST", "/plausibility-checks", json=spec)

    async def influence(self, spec: dict[str, Any]) -> StatsResponse:
        """Influence diagnostics and improbable effects of the fitted model."""
        return await self._request("POST", "/influence", json=spec)

    async def r_script(self, spec: dict[str, Any]) -> StatsResponse:
        """Reproducible R script of a saved analysis."""
        return await self._request("POST", "/r-script", json=spec)

    async def leave_one_out(self, spec: dict[str, Any]) -> StatsResponse:
        """The model refitted without each study in turn (metafor::leave1out)."""
        return await self._request("POST", "/leave-one-out", json=spec)

    async def rob_plot(self, spec: dict[str, Any]) -> StatsResponse:
        """Risk-of-bias traffic light or summary (robvis, or ggplot2 with the same look)."""
        return await self._request("POST", "/rob-plots", json=spec)


def get_stats_client() -> StatsClient:
    return StatsClient()
