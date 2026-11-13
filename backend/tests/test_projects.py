from collections.abc import Callable, Coroutine
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.integrations.email import InMemoryEmailSender
from app.modules.audit.models import AuditLog
from tests.conftest import LoggedUser, token_from_link

MakeUser = Callable[..., Coroutine[Any, Any, LoggedUser]]


async def _project(
    client: AsyncClient, user: LoggedUser, title: str = "Revisão A"
) -> dict[str, Any]:
    r = await client.post("/api/v1/projects", json={"title": title}, headers=user.headers)
    assert r.status_code == 201, r.text
    return r.json()


async def _invite_and_join(
    client: AsyncClient,
    admin: LoggedUser,
    guest: LoggedUser,
    project_id: str,
    roles: list[str],
) -> dict[str, Any]:
    r = await client.post(
        f"/api/v1/projects/{project_id}/invitations", json={"roles": roles}, headers=admin.headers
    )
    token = r.json()["link"].split("token=")[1]
    r = await client.post(f"/api/v1/invitations/{token}/accept", headers=guest.headers)
    assert r.status_code == 200, r.text
    return r.json()


async def test_creator_becomes_admin_and_owner(client: AsyncClient, make_user: MakeUser) -> None:
    ana = await make_user()
    project = await _project(client, ana)
    assert project["my_roles"] == ["admin"]
    assert project["owner_id"] == ana.id
    listed = (await client.get("/api/v1/projects", headers=ana.headers)).json()
    assert [p["id"] for p in listed] == [project["id"]]


async def test_project_changes_are_audited(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession
) -> None:
    ana = await make_user()
    project = await _project(client, ana)
    await client.patch(
        f"/api/v1/projects/{project['id']}",
        json={"version": project["version"], "title": "Novo título"},
        headers=ana.headers,
    )
    rows = (
        await session.scalars(
            select(AuditLog).where(AuditLog.entity == "projects", AuditLog.field == "title")
        )
    ).all()
    assert len(rows) == 1
    assert (rows[0].old_value, rows[0].new_value) == ("Revisão A", "Novo título")
    assert str(rows[0].user_id) == ana.id
    assert str(rows[0].project_id) == project["id"]


async def test_stale_version_is_rejected(client: AsyncClient, make_user: MakeUser) -> None:
    ana = await make_user()
    project = await _project(client, ana)
    url = f"/api/v1/projects/{project['id']}"
    ok = await client.patch(url, json={"version": 1, "title": "B"}, headers=ana.headers)
    assert ok.json()["version"] == 2
    stale = await client.patch(url, json={"version": 1, "title": "C"}, headers=ana.headers)
    assert stale.status_code == 409
    assert stale.json()["code"] == "error.version_conflict"


async def test_delete_is_soft(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession
) -> None:
    ana = await make_user()
    project = await _project(client, ana)
    r = await client.delete(f"/api/v1/projects/{project['id']}", headers=ana.headers)
    assert r.status_code == 204
    assert (
        await client.get(f"/api/v1/projects/{project['id']}", headers=ana.headers)
    ).status_code == 404
    from app.modules.projects.models import Project

    kept = await session.scalars(select(Project).execution_options(include_deleted=True))
    assert len(kept.all()) == 1


async def test_invitation_by_link_and_by_email(
    client: AsyncClient, make_user: MakeUser, outbox: InMemoryEmailSender
) -> None:
    ana = await make_user()
    bia = await make_user(email="bia@example.org")
    project = await _project(client, ana)
    r = await client.post(
        f"/api/v1/projects/{project['id']}/invitations",
        json={"email": "bia@example.org", "roles": ["reviewer", "extractor"]},
        headers=ana.headers,
    )
    assert r.status_code == 201
    assert r.json()["link"].startswith(get_settings().app_base_url)
    assert outbox.outbox[-1].to == "bia@example.org"
    token = token_from_link(outbox.outbox[-1].body)

    preview = await client.get(f"/api/v1/invitations/{token}", headers=bia.headers)
    assert preview.json()["project_title"] == "Revisão A"

    joined = await client.post(f"/api/v1/invitations/{token}/accept", headers=bia.headers)
    assert joined.json()["my_roles"] == ["reviewer", "extractor"]
    again = await client.post(f"/api/v1/invitations/{token}/accept", headers=bia.headers)
    assert again.json()["code"] == "invitation.already_accepted"


async def test_invitation_for_another_email_is_refused(
    client: AsyncClient, make_user: MakeUser
) -> None:
    ana = await make_user()
    intruder = await make_user()
    project = await _project(client, ana)
    r = await client.post(
        f"/api/v1/projects/{project['id']}/invitations",
        json={"email": "bia@example.org", "roles": ["reader"]},
        headers=ana.headers,
    )
    token = r.json()["link"].split("token=")[1]
    r = await client.post(f"/api/v1/invitations/{token}/accept", headers=intruder.headers)
    assert r.status_code == 403
    assert r.json()["code"] == "invitation.wrong_email"


async def test_expired_and_revoked_invitations(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession
) -> None:
    from datetime import UTC, datetime, timedelta

    from app.modules.projects.models import Invitation

    ana = await make_user()
    bia = await make_user()
    project = await _project(client, ana)
    url = f"/api/v1/projects/{project['id']}/invitations"
    first = (await client.post(url, json={"roles": ["reader"]}, headers=ana.headers)).json()
    second = (await client.post(url, json={"roles": ["reader"]}, headers=ana.headers)).json()

    invitation = await session.get(Invitation, first["id"])
    assert invitation is not None
    invitation.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    await session.commit()
    token = first["link"].split("token=")[1]
    r = await client.post(f"/api/v1/invitations/{token}/accept", headers=bia.headers)
    assert r.json()["code"] == "invitation.expired"

    await client.delete(f"{url}/{second['id']}", headers=ana.headers)
    token = second["link"].split("token=")[1]
    r = await client.post(f"/api/v1/invitations/{token}/accept", headers=bia.headers)
    assert r.status_code == 404
    listed = (await client.get(url, headers=ana.headers)).json()
    assert [i["id"] for i in listed] == [first["id"]]


async def test_roles_limit_what_members_can_do(client: AsyncClient, make_user: MakeUser) -> None:
    ana = await make_user()
    reader = await make_user()
    project = await _project(client, ana)
    await _invite_and_join(client, ana, reader, project["id"], ["reader"])
    base = f"/api/v1/projects/{project['id']}"

    assert (await client.get(base, headers=reader.headers)).status_code == 200
    assert (await client.get(f"{base}/members", headers=reader.headers)).status_code == 200
    r = await client.patch(base, json={"version": 1, "title": "x"}, headers=reader.headers)
    assert r.status_code == 403
    assert r.json()["code"] == "error.forbidden"
    r = await client.post(f"{base}/invitations", json={"roles": ["admin"]}, headers=reader.headers)
    assert r.status_code == 403


async def test_owner_cannot_be_removed_and_last_admin_is_kept(
    client: AsyncClient, make_user: MakeUser
) -> None:
    ana = await make_user()
    bia = await make_user()
    project = await _project(client, ana)
    await _invite_and_join(client, ana, bia, project["id"], ["admin"])
    base = f"/api/v1/projects/{project['id']}"
    members = (await client.get(f"{base}/members", headers=ana.headers)).json()
    owner = next(m for m in members if m["is_owner"])
    other = next(m for m in members if not m["is_owner"])

    r = await client.delete(f"{base}/members/{owner['id']}", headers=bia.headers)
    assert r.json()["code"] == "project.creator_cannot_be_removed"

    r = await client.post(
        f"{base}/transfer-ownership", json={"member_id": other["id"]}, headers=ana.headers
    )
    assert r.json()["owner_id"] == bia.id
    assert (
        await client.delete(f"{base}/members/{owner['id']}", headers=bia.headers)
    ).status_code == 204
    assert (await client.get(base, headers=ana.headers)).status_code == 404

    r = await client.patch(
        f"{base}/members/{other['id']}",
        json={"version": other["version"], "roles": ["reader"]},
        headers=bia.headers,
    )
    assert r.json()["code"] == "project.creator_cannot_be_removed"


async def test_admin_changes_roles_and_removes_members(
    client: AsyncClient, make_user: MakeUser
) -> None:
    ana = await make_user()
    bia = await make_user()
    project = await _project(client, ana)
    await _invite_and_join(client, ana, bia, project["id"], ["reviewer"])
    base = f"/api/v1/projects/{project['id']}"
    members = (await client.get(f"{base}/members", headers=ana.headers)).json()
    bia_member = next(m for m in members if m["user_id"] == bia.id)

    r = await client.patch(
        f"{base}/members/{bia_member['id']}",
        json={"version": bia_member["version"], "roles": ["reviewer", "extractor"]},
        headers=ana.headers,
    )
    assert r.status_code == 204
    r = await client.delete(f"{base}/members/{bia_member['id']}", headers=ana.headers)
    assert r.status_code == 204
    assert (await client.get(base, headers=bia.headers)).status_code == 404


async def test_only_owner_transfers_ownership(client: AsyncClient, make_user: MakeUser) -> None:
    ana = await make_user()
    bia = await make_user()
    project = await _project(client, ana)
    await _invite_and_join(client, ana, bia, project["id"], ["admin"])
    members = (
        await client.get(f"/api/v1/projects/{project['id']}/members", headers=ana.headers)
    ).json()
    bia_member = next(m for m in members if m["user_id"] == bia.id)
    r = await client.post(
        f"/api/v1/projects/{project['id']}/transfer-ownership",
        json={"member_id": bia_member["id"]},
        headers=bia.headers,
    )
    assert r.status_code == 403


@pytest.mark.parametrize("roles", [[], ["unknown"]])
async def test_invitation_roles_are_validated(
    client: AsyncClient, make_user: MakeUser, roles: list[str]
) -> None:
    ana = await make_user()
    project = await _project(client, ana)
    r = await client.post(
        f"/api/v1/projects/{project['id']}/invitations", json={"roles": roles}, headers=ana.headers
    )
    assert r.status_code == 422
