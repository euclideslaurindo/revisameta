"""Full text screening, exclusion reasons and included articles becoming studies
(stage 5 step 4). Every record is FICTITIOUS.
"""

from typing import Any

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models import AuditLog
from tests.test_consensus import MakeUser
from tests.test_screening import _decide, _queue, _team

FT = {"stage": "full_text"}


async def _to_full_text(
    client: AsyncClient, make_user: MakeUser
) -> tuple[Any, Any, Any, dict[str, Any], list[str]]:
    """Six references; the first four pass title and abstract (two reviewers include)."""
    ana, bia, caio, p = await _team(client, make_user)
    refs = [i["reference"]["id"] for i in (await _queue(client, bia, p))["items"]]
    for ref in refs[:4]:
        await _decide(client, bia, p, ref, "include")
        await _decide(client, caio, p, ref, "include")
    await _decide(client, bia, p, refs[4], "exclude")
    await _decide(client, caio, p, refs[4], "exclude")
    return ana, bia, caio, p, refs


async def _ft(
    client: AsyncClient,
    user: Any,
    p: dict[str, Any],
    ref: str,
    decision: str,
    reason: str | None = None,
) -> Any:
    return await client.post(
        f"{p['base']}/screening/references/{ref}/decision",
        headers=user.headers,
        params=FT,
        json={"decision": decision, "exclusion_reason_id": reason},
    )


async def _reasons(client: AsyncClient, user: Any, p: dict[str, Any]) -> list[dict[str, Any]]:
    r = await client.get(f"{p['base']}/screening/exclusion-reasons", headers=user.headers)
    assert r.status_code == 200, r.text
    data: list[dict[str, Any]] = r.json()
    return data


async def test_only_title_abstract_inclusions_reach_full_text_and_reasons_are_required(
    client: AsyncClient, make_user: MakeUser
) -> None:
    ana, bia, caio, p, refs = await _to_full_text(client, make_user)
    todo = await _queue(client, bia, p, stage="full_text")
    assert todo["total"] == 4
    assert {i["reference"]["id"] for i in todo["items"]} == set(refs[:4])
    # Excluded at title/abstract: not found at full text.
    assert (await _ft(client, bia, p, refs[4], "include")).status_code == 404

    reasons = await _reasons(client, ana, p)
    assert [r["key"] for r in reasons][:3] == [
        "wrong_population",
        "wrong_design",
        "no_comparison_group",
    ]
    pop, design = reasons[0]["id"], reasons[1]["id"]
    r = await _ft(client, bia, p, refs[0], "maybe")
    assert r.json()["code"] == "screening.no_maybe_at_full_text"
    r = await _ft(client, bia, p, refs[0], "exclude")
    assert r.json()["code"] == "screening.reason_required"

    # Same reason: excluded. Different reasons: conflict (one reason per article in PRISMA).
    await _ft(client, bia, p, refs[0], "exclude", pop)
    await _ft(client, caio, p, refs[0], "exclude", pop)
    await _ft(client, bia, p, refs[1], "exclude", pop)
    await _ft(client, caio, p, refs[1], "exclude", design)
    await _ft(client, bia, p, refs[2], "include")
    await _ft(client, caio, p, refs[2], "include")
    await _ft(client, bia, p, refs[3], "include")
    await _ft(client, caio, p, refs[3], "exclude", design)
    counts = (
        await client.get(f"{p['base']}/screening/counts", headers=ana.headers, params=FT)
    ).json()
    assert counts["exclude"] == 1 and counts["include"] == 1 and counts["conflict"] == 2

    url = f"{p['base']}/screening/references/{refs[1]}/resolution"
    r = await client.post(
        url, headers=ana.headers, params=FT, json={"decision": "exclude", "reason": "Discussed"}
    )
    assert r.json()["code"] == "screening.reason_required"
    r = await client.post(
        url,
        headers=ana.headers,
        params=FT,
        json={"decision": "exclude", "reason": "Discussed", "exclusion_reason_id": design},
    )
    assert r.json() == {"status": "resolved_exclude"}
    # Title/abstract counts are not affected by full text decisions.
    ta = (await client.get(f"{p['base']}/screening/counts", headers=ana.headers)).json()
    assert ta["include"] == 4 and ta["exclude"] == 1


async def test_reasons_rename_merge_and_remove_only_unused(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession
) -> None:
    ana, bia, caio, p, refs = await _to_full_text(client, make_user)
    base = f"{p['base']}/screening/exclusion-reasons"
    reasons = await _reasons(client, ana, p)
    pop, design, comp = reasons[0], reasons[1], reasons[2]
    await _ft(client, bia, p, refs[0], "exclude", pop["id"])
    await _ft(client, caio, p, refs[0], "exclude", design["id"])

    assert (
        await client.post(base, headers=bia.headers, json={"label": "Other"})
    ).status_code == 403
    new = (await client.post(base, headers=ana.headers, json={"label": "Animal study"})).json()
    assert new["label"] == "Animal study" and new["uses"] == 0
    r = await client.patch(
        f"{base}/{pop['id']}",
        headers=ana.headers,
        json={"label": "Other population", "version": pop["version"]},
    )
    assert r.json()["label"] == "Other population" and r.json()["key"] == "wrong_population"
    # Used reasons cannot be removed; unused ones can.
    assert (await client.delete(f"{base}/{design['id']}", headers=ana.headers)).json()[
        "code"
    ] == "reason.in_use"
    assert (await client.delete(f"{base}/{comp['id']}", headers=ana.headers)).status_code == 204
    # Merging moves the decisions: the conflict on refs[0] becomes an agreed exclusion.
    r = await client.post(
        f"{base}/{design['id']}/merge",
        headers=ana.headers,
        json={"into_id": pop["id"], "version": design["version"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["uses"] == 2
    listed = {x["id"]: x for x in await _reasons(client, ana, p)}
    assert listed[design["id"]]["merged_into_id"] == pop["id"] and comp["id"] not in listed
    counts = (
        await client.get(f"{p['base']}/screening/counts", headers=ana.headers, params=FT)
    ).json()
    assert counts["exclude"] == 1 and counts["conflict"] == 0
    # A merged reason can no longer be chosen.
    r = await _ft(client, bia, p, refs[1], "exclude", design["id"])
    assert r.json()["code"] == "screening.unknown_reason"
    audit = await session.scalars(
        select(AuditLog).where(AuditLog.entity == "exclusion_reasons", AuditLog.action == "update")
    )
    assert audit.first() is not None


async def test_included_articles_become_a_new_study_or_a_report_of_one(
    client: AsyncClient, make_user: MakeUser
) -> None:
    ana, bia, caio, p, refs = await _to_full_text(client, make_user)
    for ref in refs[:2]:
        await _ft(client, bia, p, ref, "include")
        await _ft(client, caio, p, ref, "include")
    base = f"{p['base']}/screening/included"
    waiting = (await client.get(base, headers=ana.headers)).json()
    assert {w["id"] for w in waiting} == set(refs[:2])
    body = {"mode": "new", "label": "FICTITIOUS Silva 2020", "design": "cohort_retrospective"}
    assert (
        await client.post(f"{base}/{refs[0]}/study", headers=bia.headers, json=body)
    ).status_code == 403
    r = await client.post(f"{base}/{refs[0]}/study", headers=ana.headers, json=body)
    assert r.status_code == 201, r.text
    study = r.json()
    r = await client.post(
        f"{base}/{refs[1]}/study",
        headers=ana.headers,
        json={"mode": "attach", "study_id": study["id"]},
    )
    assert r.status_code == 201 and len(r.json()["reports"]) == 2
    assert (await client.get(base, headers=ana.headers)).json() == []
    again = await client.post(f"{base}/{refs[0]}/study", headers=ana.headers, json=body)
    assert again.json()["code"] == "screening.not_waiting_for_study"
    # Removing the study keeps the screened references (their history stays).
    assert (
        await client.delete(f"{p['base']}/studies/{study['id']}", headers=ana.headers)
    ).status_code == 204
    assert {w["id"] for w in (await client.get(base, headers=ana.headers)).json()} == set(refs[:2])
