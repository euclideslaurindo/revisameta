import uuid
from collections.abc import Callable, Coroutine
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.auth.models import User
from tests.conftest import LoggedUser

MakeUser = Callable[..., Coroutine[Any, Any, LoggedUser]]


async def _create(client: AsyncClient, user: LoggedUser, title: str = "P") -> int:
    r = await client.post("/api/v1/projects", json={"title": title}, headers=user.headers)
    return r.status_code


async def test_project_quota_gives_a_clear_message(
    client: AsyncClient, make_user: MakeUser, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "quota_projects_per_user", 2)
    ana = await make_user()
    assert await _create(client, ana) == 201
    assert await _create(client, ana) == 201
    r = await client.post("/api/v1/projects", json={"title": "3"}, headers=ana.headers)
    assert r.status_code == 403
    assert r.json()["code"] == "quota.projects_exceeded"
    assert "2" in r.json()["title"]

    usage = (await client.get("/api/v1/me/usage", headers=ana.headers)).json()
    assert usage["projects"] == {"used": 2, "limit": 2}


async def test_deleted_projects_free_the_quota(
    client: AsyncClient, make_user: MakeUser, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "quota_projects_per_user", 1)
    ana = await make_user()
    project = (
        await client.post("/api/v1/projects", json={"title": "P"}, headers=ana.headers)
    ).json()
    await client.delete(f"/api/v1/projects/{project['id']}", headers=ana.headers)
    assert await _create(client, ana) == 201


async def test_system_admin_overrides_a_user_quota(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "quota_projects_per_user", 1)
    ana = await make_user()
    admin = await make_user()
    await session.execute(
        update(User).where(User.id == uuid.UUID(admin.id)).values(is_system_admin=True)
    )
    await session.commit()

    url = f"/api/v1/admin/users/{ana.id}/quotas"
    r = await client.put(url, json={"kind": "projects", "limit": 3}, headers=ana.headers)
    assert r.status_code == 403
    r = await client.put(url, json={"kind": "projects", "limit": 3}, headers=admin.headers)
    assert r.status_code == 204

    usage = (await client.get(f"/api/v1/admin/users/{ana.id}/usage", headers=admin.headers)).json()
    assert usage["projects"]["limit"] == 3
    assert usage["storage_mb"]["used"] == 0
    for _ in range(3):
        assert await _create(client, ana) == 201

    r = await client.put(url, json={"kind": "projects", "limit": None}, headers=admin.headers)
    assert (await client.get("/api/v1/me/usage", headers=ana.headers)).json()["projects"][
        "limit"
    ] == 1


async def test_admin_routes_return_404_for_unknown_user(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession
) -> None:
    admin = await make_user()
    await session.execute(
        update(User).where(User.id == uuid.UUID(admin.id)).values(is_system_admin=True)
    )
    await session.commit()
    missing = uuid.uuid4()
    assert (
        await client.get(f"/api/v1/admin/users/{missing}/usage", headers=admin.headers)
    ).status_code == 404
    r = await client.put(
        f"/api/v1/admin/users/{missing}/quotas",
        json={"kind": "projects", "limit": 1},
        headers=admin.headers,
    )
    assert r.status_code == 404
