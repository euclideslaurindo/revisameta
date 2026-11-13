"""Test fixtures. Tests run against a real Postgres (compose profile "test")."""

from collections.abc import AsyncIterator

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base
from app.db.session import dispose_engine, get_engine, get_sessionmaker
from app.main import app as fastapi_app


@pytest.fixture(scope="session", autouse=True)
async def _database() -> AsyncIterator[None]:
    """Run every migration once, exactly like a deploy does."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    config = Config("alembic.ini")
    await engine.dispose()
    await _run_in_thread(command.upgrade, config, "head")
    yield
    await dispose_engine()


async def _run_in_thread(fn: object, *args: object) -> None:
    import asyncio

    await asyncio.to_thread(fn, *args)  # type: ignore[arg-type]


@pytest.fixture(autouse=True)
async def _clean_tables() -> AsyncIterator[None]:
    yield
    tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    async with get_engine().begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as s:
        yield s


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


# ---- Auth helpers -----------------------------------------------------------

from dataclasses import dataclass  # noqa: E402
from urllib.parse import parse_qs, urlparse  # noqa: E402

from redis.asyncio import Redis  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.integrations.email import InMemoryEmailSender, get_email_sender  # noqa: E402

PASSWORD = "senha-forte-123"


@pytest.fixture(autouse=True)
async def _fresh_redis() -> AsyncIterator[None]:
    """Rate-limit and failed-login counters start empty in every test."""
    async with Redis.from_url(get_settings().redis_url) as redis:
        await redis.flushdb()
    yield


@pytest.fixture(autouse=True)
def outbox() -> AsyncIterator[InMemoryEmailSender]:  # type: ignore[misc]
    sender = InMemoryEmailSender()
    fastapi_app.dependency_overrides[get_email_sender] = lambda: sender
    yield sender
    fastapi_app.dependency_overrides.pop(get_email_sender, None)


def token_from_link(body: str) -> str:
    link = next(line for line in body.splitlines() if "token=" in line)
    return parse_qs(urlparse(link.strip()).query)["token"][0]


@dataclass
class LoggedUser:
    id: str
    email: str
    token: str

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


@pytest.fixture
def make_user(client: AsyncClient, outbox: InMemoryEmailSender):  # type: ignore[no-untyped-def]
    counter = 0

    async def _make(name: str = "Pessoa", email: str | None = None) -> LoggedUser:
        nonlocal counter
        counter += 1
        email = email or f"pessoa{counter}@example.org"
        r = await client.post(
            "/api/v1/auth/register",
            json={
                "name": name,
                "email": email,
                "password": PASSWORD,
                "accept_terms": True,
                "captcha_token": "good",
            },
        )
        assert r.status_code == 201, r.text
        await client.post(
            "/api/v1/auth/verify-email", json={"token": token_from_link(outbox.outbox[-1].body)}
        )
        r = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
        assert r.status_code == 200, r.text
        return LoggedUser(id=r.json()["user"]["id"], email=email, token=r.json()["access_token"])

    return _make
