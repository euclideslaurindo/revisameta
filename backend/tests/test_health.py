from collections.abc import Iterator

import httpx
import pytest
from httpx import AsyncClient

from app.integrations.stats_client import StatsClient, get_stats_client
from app.main import app
from tests.test_stats_client import HEALTH


@pytest.fixture
def stats_up() -> Iterator[None]:
    transport = httpx.MockTransport(lambda _r: httpx.Response(200, json=HEALTH))
    app.dependency_overrides[get_stats_client] = lambda: StatsClient(
        "http://r", transport=transport
    )
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def stats_down(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    from app.integrations import stats_client

    monkeypatch.setattr(stats_client, "BACKOFF_SECONDS", 0)

    def fail(_r: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    transport = httpx.MockTransport(fail)
    app.dependency_overrides[get_stats_client] = lambda: StatsClient(
        "http://r", transport=transport
    )
    yield
    app.dependency_overrides.clear()


async def test_liveness(client: AsyncClient) -> None:
    r = await client.get("/api/v1/health/live")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


async def test_health_reports_every_dependency(client: AsyncClient, stats_up: None) -> None:
    r = await client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["checks"]["database"]["status"] == "ok"
    assert body["checks"]["redis"]["status"] == "ok"
    assert body["checks"]["stats_r"]["r_version"] == "4.6.2"


async def test_health_is_503_when_r_is_down(client: AsyncClient, stats_down: None) -> None:
    r = await client.get("/api/v1/health")
    assert r.status_code == 503
    assert r.json()["checks"]["stats_r"]["status"] == "down"


async def test_responses_carry_a_request_id(client: AsyncClient) -> None:
    r = await client.get("/api/v1/health/live")
    assert len(r.headers["X-Request-ID"]) == 32
