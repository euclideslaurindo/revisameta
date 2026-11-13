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
