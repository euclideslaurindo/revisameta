import httpx
import pytest

from app.core.errors import ServiceUnavailableError
from app.core.logging import request_id_var
from app.integrations import stats_client as module
from app.integrations.stats_client import StatsClient

HEALTH = {
    "ok": True,
    "result": {"status": "ok"},
    "warnings": [],
    "errors": [],
    "meta": {
        "r_version": "4.6.2",
        "packages": {"metafor": "4.8-0", "robvis": "0.3.0.900"},
        "robvis_commit": "0c59cf1",
        "params": {},
    },
}


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module, "BACKOFF_SECONDS", 0)


async def test_health_parses_the_standard_envelope_and_sends_request_id() -> None:
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("X-Request-ID"))
        return httpx.Response(200, json=HEALTH)

    token = request_id_var.set("req-42")
    try:
        result = await StatsClient("http://r", transport=httpx.MockTransport(handler)).health()
    finally:
        request_id_var.reset(token)
    assert result.ok
    assert result.meta.r_version == "4.6.2"
    assert seen == ["req-42"]


async def test_retries_then_succeeds() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise httpx.ConnectError("down")
        return httpx.Response(200, json=HEALTH)

    result = await StatsClient("http://r", transport=httpx.MockTransport(handler)).health()
    assert result.ok
    assert calls == 3


async def test_gives_a_clear_error_when_r_is_down() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    with pytest.raises(ServiceUnavailableError):
        await StatsClient("http://r", transport=httpx.MockTransport(handler)).health()


async def test_invalid_payload_is_treated_as_unavailable() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="<html>")

    with pytest.raises(ServiceUnavailableError):
        await StatsClient("http://r", transport=httpx.MockTransport(handler)).health()


async def test_503_from_r_is_parsed_not_retried() -> None:
    degraded = {**HEALTH, "ok": False, "errors": ["Package not available: robvis"]}

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json=degraded)

    result = await StatsClient("http://r", transport=httpx.MockTransport(handler)).health()
    assert not result.ok
    assert result.errors == ["Package not available: robvis"]
