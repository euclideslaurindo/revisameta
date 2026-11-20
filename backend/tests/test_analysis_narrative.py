"""Narrative synthesis (stage 4 step 4): studies left out of the meta-analysis with the
direction of the effect recorded by a reviewer. FICTITIOUS studies; the real R service
computes the assembly, but no number is checked here.
"""

from typing import Any

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models import AuditLog
from tests.test_analysis_assembly import _setup
from tests.test_consensus import MakeUser, _join

GOOD = {"n": 30, "mean": 92.0, "sd": 12.0, "dispersion_type": "sd"}
OTHER = {"n": 32, "mean": 85.0, "sd": 11.0, "dispersion_type": "sd"}


async def _table(client: AsyncClient, user: Any, p: dict[str, Any]) -> dict[str, Any]:
    r = await client.post(
        f"{p['base']}/analyses/narrative",
        headers=user.headers,
        json={"outcome_id": p["outcome"], "timepoint": "5 anos"},
    )
    assert r.status_code == 200, r.text
    data: dict[str, Any] = r.json()
    return data


async def test_left_out_studies_get_a_direction_recorded_by_a_person(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession
) -> None:
    ana, p, seed = await _setup(client, make_user, session)
    await seed.study("A ok", [(0, GOOD), (1, OTHER)])
    await seed.study("B ok", [(0, GOOD), (1, OTHER)])
    left = await seed.study("C sem grupo 2", [(0, GOOD), (-1, OTHER)])
    table = await _table(client, ana, p)
    labels = {r["label"]: r for r in table["rows"]}
    # Included studies do not appear; the left-out ones come with their reasons.
    assert "A ok" not in labels and "C sem grupo 2" in labels
    row = labels["C sem grupo 2"]
    assert row["direction"] is None and row["reasons"] == ["missing_group"]
    assert table["missing"] == len(table["rows"])

    url = f"{p['base']}/analyses/narrative/{left}"
    body = {"outcome_id": p["outcome"], "timepoint": "5 anos", "direction": "favours_group1"}
    r = await client.put(url, headers=ana.headers, json={**body, "note": "Tabela 3"})
    assert r.status_code == 200, r.text
    saved = r.json()
    assert saved["direction"] == "favours_group1" and saved["version"] == 1
    # Editing needs the version read (optimistic lock).
    stale = await client.put(url, headers=ana.headers, json={**body, "direction": "mixed"})
    assert stale.status_code == 409
    r = await client.put(
        url, headers=ana.headers, json={**body, "direction": "mixed", "version": 1}
    )
    assert r.json()["direction"] == "mixed" and r.json()["version"] == 2
    row = {x["label"]: x for x in (await _table(client, ana, p))["rows"]}["C sem grupo 2"]
    assert row["direction"] == "mixed" and row["note"] is None
    audit = await session.scalars(select(AuditLog).where(AuditLog.entity == "narrative_entries"))
    assert audit.first() is not None
    bad = await client.put(url, headers=ana.headers, json={**body, "direction": "probably"})
    assert bad.status_code == 422


async def test_readers_and_reviewers_only_read(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession
) -> None:
    ana, p, seed = await _setup(client, make_user, session)
    left = await seed.study("C sem grupo 2", [(0, GOOD), (-1, OTHER)])
    body = {"outcome_id": p["outcome"], "timepoint": "5 anos", "direction": "not_reported"}
    for roles, status in ((["reader"], 403), (["reviewer"], 403), (["extractor"], 200)):
        user = await make_user()
        await _join(client, ana, user, p["pid"], roles)
        await _table(client, user, p)
        r = await client.put(
            f"{p['base']}/analyses/narrative/{left}", headers=user.headers, json=body
        )
        assert r.status_code == status, (roles, r.text)
