"""The AI gateway (stage 7 step 3): cache, per-user quota and global limits.
Only the fake provider is used."""

import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError
from app.integrations.ai import FakeProvider
from app.integrations.ai.base import AIQuotaExceededError
from app.modules.ai import gateway
from app.modules.ai.notice import VERSION
from app.modules.auth.models import User
from app.modules.projects.access import ProjectContext
from app.modules.projects.models import Project, ProjectMember
from tests.test_consensus import MakeUser, _project


class Answer(BaseModel):
    text: str


async def _ctx(client: AsyncClient, make_user: MakeUser, session: AsyncSession) -> Any:
    ana = await make_user("Ana")
    p = await _project(client, ana)
    await client.put(
        f"{p['base']}/ai/settings",
        headers=ana.headers,
        json={"enabled": True, "accept_notice_version": VERSION},
    )
    project = await session.get(Project, uuid.UUID(p["pid"]))
    user = await session.get(User, uuid.UUID(ana.id))
    member = (
        await session.scalars(select(ProjectMember).where(ProjectMember.project_id == project.id))  # type: ignore[union-attr]
    ).first()
    return ana, p, ProjectContext(project=project, member=member, user=user)  # type: ignore[arg-type]


async def _ask(session: AsyncSession, ctx: Any, fake: FakeProvider, prompt: str = "p") -> Any:
    return await gateway.call(
        session,
        ctx,
        fake,
        function="tutor",
        prompt_version="tutor-v1",
        system="s",
        prompt=prompt,
        schema=Answer,
    )


@pytest.fixture(autouse=True)
def _fake_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "ai_provider", "fake")


async def test_cache_spends_quota_once(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession
) -> None:
    ana, _, ctx = await _ctx(client, make_user, session)
    fake = FakeProvider()
    fake.will_answer('{"text": "olá"}')
    first = await _ask(session, ctx, fake)
    second = await _ask(session, ctx, fake)
    assert first.answer.text == second.answer.text == "olá"
    assert (first.cached, second.cached) == (False, True)
    assert len(fake.calls) == 1
    usage = (await client.get("/api/v1/me/usage", headers=ana.headers)).json()
    assert usage["ai_calls"] == {"used": 1, "limit": 30}


async def test_quota_per_user_and_global_limits(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, ctx = await _ctx(client, make_user, session)
    fake = FakeProvider()
    monkeypatch.setattr(get_settings(), "ai_calls_per_user_day", 2)
    fake.will_answer('{"text": "1"}', '{"text": "2"}')
    await _ask(session, ctx, fake, "a")
    await _ask(session, ctx, fake, "b")
    with pytest.raises(AppError) as error:
        await _ask(session, ctx, fake, "c")
    assert error.value.code == "ai.quota_exceeded" and len(fake.calls) == 2

    monkeypatch.setattr(get_settings(), "ai_calls_per_user_day", 100)
    monkeypatch.setattr(get_settings(), "ai_calls_per_minute", 3)
    fake.will_answer('{"text": "3"}')
    await _ask(session, ctx, fake, "d")
    with pytest.raises(AppError) as error:
        await _ask(session, ctx, fake, "e")  # 4th call in the minute, shared by everyone
    assert error.value.code == "ai.quota_exceeded" and len(fake.calls) == 3


async def test_provider_errors_and_invalid_output(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession
) -> None:
    _, _, ctx = await _ctx(client, make_user, session)
    fake = FakeProvider()
    fake.will_answer(AIQuotaExceededError(), '{"wrong": 1}')
    with pytest.raises(AppError) as error:
        await _ask(session, ctx, fake, "x")
    assert error.value.code == "ai.quota_exceeded"
    with pytest.raises(AppError) as error:
        await _ask(session, ctx, fake, "y")
    assert error.value.code == "ai.invalid_output"


async def test_off_project_never_calls_the_provider(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession
) -> None:
    ana, p, ctx = await _ctx(client, make_user, session)
    settings = (await client.get(f"{p['base']}/ai/settings", headers=ana.headers)).json()
    await client.put(
        f"{p['base']}/ai/settings",
        headers=ana.headers,
        json={"enabled": False, "version": settings["version"]},
    )
    session.expunge_all()
    project = await session.get(Project, ctx.project.id)
    off = ProjectContext(project=project, member=ctx.member, user=ctx.user)  # type: ignore[arg-type]
    fake = FakeProvider()
    with pytest.raises(AppError) as error:
        await _ask(session, off, fake)
    assert error.value.code == "ai.disabled" and fake.calls == []
