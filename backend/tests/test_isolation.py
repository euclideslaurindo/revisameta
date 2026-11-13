"""Project isolation (CLAUDE.md 0.1, rule 10; docs/validacao.md, 11.2).

Every project route is listed here. A user who is not a member must get 404 on all
of them, including a system administrator. When a new project route is added,
add it to PROJECT_ROUTES; `test_every_project_route_is_covered` fails otherwise.
"""

import uuid
from collections.abc import Callable, Coroutine
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.modules.auth.models import User
from tests.conftest import LoggedUser

MakeUser = Callable[..., Coroutine[Any, Any, LoggedUser]]

PROJECT_ROUTES: list[tuple[str, str, dict[str, Any] | None]] = [
    ("GET", "/api/v1/projects/{project_id}", None),
    ("PATCH", "/api/v1/projects/{project_id}", {"version": 1, "title": "hack"}),
    ("DELETE", "/api/v1/projects/{project_id}", None),
    ("POST", "/api/v1/projects/{project_id}/transfer-ownership", {"member_id": "{member_id}"}),
    ("GET", "/api/v1/projects/{project_id}/members", None),
    (
        "PATCH",
        "/api/v1/projects/{project_id}/members/{member_id}",
        {"version": 1, "roles": ["admin"]},
    ),
    ("DELETE", "/api/v1/projects/{project_id}/members/{member_id}", None),
    ("POST", "/api/v1/projects/{project_id}/invitations", {"roles": ["admin"]}),
    ("GET", "/api/v1/projects/{project_id}/invitations", None),
    ("DELETE", "/api/v1/projects/{project_id}/invitations/{invitation_id}", None),
]


def test_every_project_route_is_covered() -> None:
    paths = app.openapi()["paths"]
    registered = {
        (method.upper(), path)
        for path, operations in paths.items()
        if "{project_id}" in path
        for method in operations
    }
    covered = {(method, path) for method, path, _ in PROJECT_ROUTES}
    assert registered == covered


async def _setup(client: AsyncClient, make_user: MakeUser) -> tuple[LoggedUser, dict[str, str]]:
    owner = await make_user()
    project = (
        await client.post("/api/v1/projects", json={"title": "Secreto"}, headers=owner.headers)
    ).json()
    members = (
        await client.get(f"/api/v1/projects/{project['id']}/members", headers=owner.headers)
    ).json()
    invitation = (
        await client.post(
            f"/api/v1/projects/{project['id']}/invitations",
            json={"roles": ["reader"]},
            headers=owner.headers,
        )
    ).json()
    ids = {
        "project_id": project["id"],
        "member_id": members[0]["id"],
        "invitation_id": invitation["id"],
    }
    return owner, ids


def _fill(value: Any, ids: dict[str, str]) -> Any:
    if isinstance(value, str):
        return value.format(**ids)
    if isinstance(value, dict):
        return {k: _fill(v, ids) for k, v in value.items()}
    return value


@pytest.mark.parametrize(("method", "path", "body"), PROJECT_ROUTES)
async def test_outsider_gets_404_on_every_project_route(
    client: AsyncClient, make_user: MakeUser, method: str, path: str, body: dict[str, Any] | None
) -> None:
    _owner, ids = await _setup(client, make_user)
    outsider = await make_user()
    r = await client.request(
        method, _fill(path, ids), json=_fill(body, ids), headers=outsider.headers
    )
    assert r.status_code == 404, r.text


@pytest.mark.parametrize(("method", "path", "body"), PROJECT_ROUTES)
async def test_system_admin_is_not_a_backdoor(
    client: AsyncClient,
    make_user: MakeUser,
    session: AsyncSession,
    method: str,
    path: str,
    body: dict[str, Any] | None,
) -> None:
    _owner, ids = await _setup(client, make_user)
    sysadmin = await make_user()
    await session.execute(
        update(User).where(User.id == uuid.UUID(sysadmin.id)).values(is_system_admin=True)
    )
    await session.commit()
    r = await client.request(
        method, _fill(path, ids), json=_fill(body, ids), headers=sysadmin.headers
    )
    assert r.status_code == 404, r.text


async def test_anonymous_gets_401(client: AsyncClient, make_user: MakeUser) -> None:
    _owner, ids = await _setup(client, make_user)
    r = await client.get(f"/api/v1/projects/{ids['project_id']}")
    assert r.status_code == 401


async def test_ids_from_another_project_are_not_reachable(
    client: AsyncClient, make_user: MakeUser
) -> None:
    """Admin of project B cannot touch members/invitations of project A through B's URL."""
    _owner_a, ids_a = await _setup(client, make_user)
    owner_b = await make_user()
    project_b = (
        await client.post("/api/v1/projects", json={"title": "B"}, headers=owner_b.headers)
    ).json()
    base_b = f"/api/v1/projects/{project_b['id']}"
    r = await client.delete(f"{base_b}/members/{ids_a['member_id']}", headers=owner_b.headers)
    assert r.status_code == 404
    r = await client.delete(
        f"{base_b}/invitations/{ids_a['invitation_id']}", headers=owner_b.headers
    )
    assert r.status_code == 404
    listed = (await client.get("/api/v1/projects", headers=owner_b.headers)).json()
    assert [p["id"] for p in listed] == [project_b["id"]]
