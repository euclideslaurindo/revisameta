"""AI on/off per project with the data-use notice (stage 7 step 2)."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError
from app.modules.ai import settings as ai
from app.modules.ai.notice import VERSION
from app.modules.audit.models import AuditLog
from tests.test_consensus import MakeUser, _join, _project


async def test_off_by_default_and_on_only_with_the_notice(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession
) -> None:
    ana = await make_user("Ana")
    p = await _project(client, ana)
    url = f"{p['base']}/ai/settings"
    out = (await client.get(url, headers=ana.headers)).json()
    assert out["enabled"] is False and out["accepted_version"] is None
    assert out["notice_version"] == VERSION
    assert "Google" in " ".join(out["notice"]["pt-BR"]["paragraphs"])

    r = await client.put(url, headers=ana.headers, json={"enabled": True})
    assert r.status_code == 422 and r.json()["code"] == "ai.notice_required"
    r = await client.put(
        url, headers=ana.headers, json={"enabled": True, "accept_notice_version": "old"}
    )
    assert r.json()["code"] == "ai.notice_required"

    bia = await make_user("Bia")
    await _join(client, ana, bia, p["pid"], ["reviewer"])
    on = {"enabled": True, "accept_notice_version": VERSION}
    assert (await client.put(url, headers=bia.headers, json=on)).status_code == 403
    out = (await client.put(url, headers=ana.headers, json=on)).json()
    assert out["enabled"] is True and out["accepted_by_name"] == "Ana"
    assert out["accepted_version"] == VERSION and out["accepted_at"]
    # The acceptance is in the audit log.
    audit = await session.scalars(select(AuditLog).where(AuditLog.entity == "ai_settings"))
    assert audit.first() is not None

    # Stale version conflicts; turning off needs no notice.
    assert (await client.put(url, headers=ana.headers, json=on)).status_code == 409
    off = {"enabled": False, "version": out["version"]}
    assert (await client.put(url, headers=ana.headers, json=off)).json()["enabled"] is False


async def test_require_refuses_before_any_provider_call(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.modules.auth.models import User
    from app.modules.projects.access import ProjectContext
    from app.modules.projects.models import Project, ProjectMember

    ana = await make_user("Ana")
    p = await _project(client, ana)
    project = await session.get(Project, __import__("uuid").UUID(p["pid"]))
    user = await session.get(User, __import__("uuid").UUID(ana.id))
    member = (
        await session.scalars(select(ProjectMember).where(ProjectMember.project_id == project.id))  # type: ignore[union-attr]
    ).first()
    ctx = ProjectContext(project=project, member=member, user=user)  # type: ignore[arg-type]

    with pytest.raises(AppError) as error:
        await ai.require(session, ctx, "tutor")
    assert error.value.code == "ai.disabled"

    url = f"{p['base']}/ai/settings"
    on = {"enabled": True, "accept_notice_version": VERSION, "functions": ["tutor"]}
    await client.put(url, headers=ana.headers, json=on)
    with pytest.raises(AppError) as error:
        await ai.require(session, ctx, "locate")
    assert error.value.code == "ai.function_disabled"

    monkeypatch.setattr(get_settings(), "ai_provider", "none")
    with pytest.raises(AppError) as error:
        await ai.require(session, ctx, "tutor")
    assert error.value.code == "ai.unavailable"
    monkeypatch.setattr(get_settings(), "ai_provider", "fake")
    assert (await ai.require(session, ctx, "tutor")).enabled is True

    # A new notice version makes the earlier acceptance stop counting.
    monkeypatch.setattr(ai, "VERSION", "2099-01-01")
    with pytest.raises(AppError) as error:
        await ai.require(session, ctx, "tutor")
    assert error.value.code == "ai.disabled"
