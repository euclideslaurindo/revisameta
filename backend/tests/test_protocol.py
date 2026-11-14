from collections.abc import Callable, Coroutine
from typing import Any

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models import AuditLog
from tests.conftest import LoggedUser

MakeUser = Callable[..., Coroutine[Any, Any, LoggedUser]]


async def _project(client: AsyncClient, user: LoggedUser) -> str:
    r = await client.post("/api/v1/projects", json={"title": "P"}, headers=user.headers)
    return str(r.json()["id"])


async def _join(
    client: AsyncClient, admin: LoggedUser, guest: LoggedUser, pid: str, roles: list[str]
) -> None:
    r = await client.post(
        f"/api/v1/projects/{pid}/invitations", json={"roles": roles}, headers=admin.headers
    )
    token = r.json()["link"].split("token=")[1]
    await client.post(f"/api/v1/invitations/{token}/accept", headers=guest.headers)


async def test_double_extraction_is_on_by_default_and_admin_can_turn_it_off(
    client: AsyncClient, make_user: MakeUser
) -> None:
    ana = await make_user()
    pid = await _project(client, ana)
    project = (await client.get(f"/api/v1/projects/{pid}", headers=ana.headers)).json()
    assert project["double_extraction"] is True
    r = await client.patch(
        f"/api/v1/projects/{pid}",
        json={"version": project["version"], "double_extraction": False},
        headers=ana.headers,
    )
    assert r.json()["double_extraction"] is False


async def test_outcomes_crud_with_clean_timepoints_and_audit(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession
) -> None:
    ana = await make_user()
    pid = await _project(client, ana)
    base = f"/api/v1/projects/{pid}/outcomes"
    r = await client.post(
        base,
        json={
            "name": " Desfecho cognitivo ",
            "type": "continuous",
            "is_primary": True,
            "timepoints": ["12 meses", " 12 MESES", "", "5 anos"],
        },
        headers=ana.headers,
    )
    assert r.status_code == 201
    outcome = r.json()
    assert outcome["name"] == "Desfecho cognitivo"
    assert outcome["timepoints"] == ["12 meses", "5 anos"]
    assert outcome["higher_is_better"] is True

    r = await client.patch(
        f"{base}/{outcome['id']}",
        json={"version": 1, "higher_is_better": False},
        headers=ana.headers,
    )
    assert r.json()["higher_is_better"] is False
    stale = await client.patch(
        f"{base}/{outcome['id']}", json={"version": 1, "name": "x"}, headers=ana.headers
    )
    assert stale.status_code == 409

    assert (await client.delete(f"{base}/{outcome['id']}", headers=ana.headers)).status_code == 204
    assert (await client.get(base, headers=ana.headers)).json() == []
    actions = (
        await session.scalars(select(AuditLog.action).where(AuditLog.entity == "outcomes"))
    ).all()
    assert set(actions) == {"create", "update", "delete"}


async def test_names_are_unique_per_project_case_insensitive(
    client: AsyncClient, make_user: MakeUser
) -> None:
    ana = await make_user()
    pid = await _project(client, ana)
    groups = f"/api/v1/projects/{pid}/comparison-groups"
    await client.post(groups, json={"label": "Cirurgia < 5 anos"}, headers=ana.headers)
    r = await client.post(groups, json={"label": "cirurgia < 5 ANOS"}, headers=ana.headers)
    assert r.status_code == 409
    assert r.json()["code"] == "protocol.duplicate_name"

    other = await _project(client, ana)
    r = await client.post(
        f"/api/v1/projects/{other}/comparison-groups",
        json={"label": "Cirurgia < 5 anos"},
        headers=ana.headers,
    )
    assert r.status_code == 201


async def test_groups_ordered_and_editable(client: AsyncClient, make_user: MakeUser) -> None:
    ana = await make_user()
    pid = await _project(client, ana)
    base = f"/api/v1/projects/{pid}/comparison-groups"
    late = (
        await client.post(base, json={"label": ">= 5 anos", "position": 2}, headers=ana.headers)
    ).json()
    await client.post(
        base,
        json={"label": "< 5 anos", "position": 1, "rule_description": "Idade na cirurgia"},
        headers=ana.headers,
    )
    labels = [g["label"] for g in (await client.get(base, headers=ana.headers)).json()]
    assert labels == ["< 5 anos", ">= 5 anos"]
    r = await client.patch(
        f"{base}/{late['id']}", json={"version": 1, "label": "5 anos ou mais"}, headers=ana.headers
    )
    assert r.json()["label"] == "5 anos ou mais"
    assert (await client.delete(f"{base}/{late['id']}", headers=ana.headers)).status_code == 204


async def test_only_admins_change_the_protocol(client: AsyncClient, make_user: MakeUser) -> None:
    ana = await make_user()
    extractor = await make_user()
    pid = await _project(client, ana)
    await _join(client, ana, extractor, pid, ["extractor"])
    base = f"/api/v1/projects/{pid}/outcomes"
    assert (await client.get(base, headers=extractor.headers)).status_code == 200
    r = await client.post(
        base, json={"name": "QI", "type": "continuous"}, headers=extractor.headers
    )
    assert r.status_code == 403


async def test_invalid_outcome_type_is_rejected(client: AsyncClient, make_user: MakeUser) -> None:
    ana = await make_user()
    pid = await _project(client, ana)
    r = await client.post(
        f"/api/v1/projects/{pid}/outcomes",
        json={"name": "X", "type": "time_to_event"},
        headers=ana.headers,
    )
    assert r.status_code == 422
