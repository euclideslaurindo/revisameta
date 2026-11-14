"""Project isolation (CLAUDE.md 0.1, rule 10; docs/validacao.md, 11.2).

Every project route is listed here. A user who is not a member must get 404 on all
of them, including a system administrator. When a new project route is added,
add it to PROJECT_ROUTES; `test_every_project_route_is_covered` fails otherwise.
"""

import uuid
from collections.abc import Callable, Coroutine
from typing import Any

import httpx
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
    ("POST", "/api/v1/projects/{project_id}/uploads", {"filename": "a.pdf", "size_bytes": 10}),
    ("GET", "/api/v1/projects/{project_id}/uploads/{upload_id}", None),
    ("DELETE", "/api/v1/projects/{project_id}/uploads/{upload_id}", None),
    ("POST", "/api/v1/projects/{project_id}/uploads/{upload_id}/parts", {"part_numbers": [1]}),
    ("POST", "/api/v1/projects/{project_id}/uploads/{upload_id}/complete", None),
    ("GET", "/api/v1/projects/{project_id}/uploads/{upload_id}/download-url", None),
    ("GET", "/api/v1/projects/{project_id}/jobs/{job_id}", None),
    ("GET", "/api/v1/projects/{project_id}/jobs/{job_id}/events", None),
    ("GET", "/api/v1/projects/{project_id}/outcomes", None),
    ("POST", "/api/v1/projects/{project_id}/outcomes", {"name": "QI", "type": "continuous"}),
    ("PATCH", "/api/v1/projects/{project_id}/outcomes/{outcome_id}", {"version": 1, "name": "x"}),
    ("DELETE", "/api/v1/projects/{project_id}/outcomes/{outcome_id}", None),
    ("GET", "/api/v1/projects/{project_id}/comparison-groups", None),
    ("POST", "/api/v1/projects/{project_id}/comparison-groups", {"label": "< 5 anos"}),
    (
        "PATCH",
        "/api/v1/projects/{project_id}/comparison-groups/{group_id}",
        {"version": 1, "label": "x"},
    ),
    ("DELETE", "/api/v1/projects/{project_id}/comparison-groups/{group_id}", None),
    ("GET", "/api/v1/projects/{project_id}/studies", None),
    (
        "POST",
        "/api/v1/projects/{project_id}/studies",
        {"label": "X", "design": "other", "reference": {"title": "T"}},
    ),
    ("GET", "/api/v1/projects/{project_id}/studies/{study_id}", None),
    ("PATCH", "/api/v1/projects/{project_id}/studies/{study_id}", {"version": 1, "label": "Y"}),
    ("DELETE", "/api/v1/projects/{project_id}/studies/{study_id}", None),
    (
        "POST",
        "/api/v1/projects/{project_id}/studies/{study_id}/reports",
        {"reference": {"title": "T2"}},
    ),
    ("DELETE", "/api/v1/projects/{project_id}/studies/{study_id}/reports/{report_id}", None),
    (
        "POST",
        "/api/v1/projects/{project_id}/studies/{study_id}/merge",
        {"other_study_id": "{study_id}"},
    ),
    (
        "PATCH",
        "/api/v1/projects/{project_id}/references/{reference_id}",
        {"version": 1, "title": "Z"},
    ),
    ("POST", "/api/v1/projects/{project_id}/study-imports/preview", None),
    ("POST", "/api/v1/projects/{project_id}/study-imports", None),
    (
        "POST",
        "/api/v1/projects/{project_id}/reports/{report_id}/pdfs",
        {"upload_id": "{upload_id}"},
    ),
    ("GET", "/api/v1/projects/{project_id}/reports/{report_id}/pdfs", None),
    ("GET", "/api/v1/projects/{project_id}/pdfs/{pdf_id}", None),
    ("DELETE", "/api/v1/projects/{project_id}/pdfs/{pdf_id}", None),
    ("GET", "/api/v1/projects/{project_id}/pdfs/{pdf_id}/search?q=teste", None),
    ("GET", "/api/v1/projects/{project_id}/pdfs/{pdf_id}/annotations", None),
    ("POST", "/api/v1/projects/{project_id}/pdfs/{pdf_id}/annotations", {"page": 1, "quote": "x"}),
    (
        "PATCH",
        "/api/v1/projects/{project_id}/annotations/{annotation_id}",
        {"version": 1, "note": "x"},
    ),
    ("DELETE", "/api/v1/projects/{project_id}/annotations/{annotation_id}", None),
]


def test_every_project_route_is_covered() -> None:
    paths = app.openapi()["paths"]
    registered = {
        (method.upper(), path)
        for path, operations in paths.items()
        if "{project_id}" in path
        for method in operations
    }
    covered = {(method, path.split("?")[0]) for method, path, _ in PROJECT_ROUTES}
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
    base = f"/api/v1/projects/{project['id']}/uploads"
    content = b"%PDF-1.7 " + b"0" * 100
    upload = (
        await client.post(
            base, json={"filename": "a.pdf", "size_bytes": len(content)}, headers=owner.headers
        )
    ).json()
    urls = (
        await client.post(
            f"{base}/{upload['id']}/parts", json={"part_numbers": [1]}, headers=owner.headers
        )
    ).json()
    async with httpx.AsyncClient() as raw:
        await raw.put(urls[0]["url"], content=content)
    job = (await client.post(f"{base}/{upload['id']}/complete", headers=owner.headers)).json()
    ids = {
        "project_id": project["id"],
        "member_id": members[0]["id"],
        "invitation_id": invitation["id"],
        "upload_id": upload["id"],
        "job_id": job["id"],
        "outcome_id": (
            await client.post(
                f"/api/v1/projects/{project['id']}/outcomes",
                json={"name": "Desfecho", "type": "continuous"},
                headers=owner.headers,
            )
        ).json()["id"],
        **(study_ids := await _study_ids(client, owner, project["id"])),
        **(await _pdf_ids(client, owner, project["id"], study_ids["report_id"], upload["id"])),
        "group_id": (
            await client.post(
                f"/api/v1/projects/{project['id']}/comparison-groups",
                json={"label": "Grupo"},
                headers=owner.headers,
            )
        ).json()["id"],
    }
    return owner, ids


async def _study_ids(client: AsyncClient, owner: LoggedUser, project_id: str) -> dict[str, str]:
    study = (
        await client.post(
            f"/api/v1/projects/{project_id}/studies",
            json={"label": "Estudo A", "design": "other", "reference": {"title": "Artigo A"}},
            headers=owner.headers,
        )
    ).json()
    report = study["reports"][0]
    return {
        "study_id": study["id"],
        "report_id": report["id"],
        "reference_id": report["reference"]["id"],
    }


async def _pdf_ids(
    client: AsyncClient, owner: LoggedUser, project_id: str, report_id: str, upload_id: str
) -> dict[str, str]:
    base = f"/api/v1/projects/{project_id}"
    pdf = (
        await client.post(
            f"{base}/reports/{report_id}/pdfs", json={"upload_id": upload_id}, headers=owner.headers
        )
    ).json()
    annotation = (
        await client.post(
            f"{base}/pdfs/{pdf['id']}/annotations",
            json={"page": 1, "quote": "trecho"},
            headers=owner.headers,
        )
    ).json()
    return {"pdf_id": pdf["id"], "annotation_id": annotation["id"]}


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
