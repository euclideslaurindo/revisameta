"""Title and abstract screening (stage 5 step 3; docs/validacao.md 11.2).

Every record is FICTITIOUS. Covers: double screening and the approved conflict rule,
blinding through the API, undo restoring the previous decision (with audit), batches,
the "useful as reference" marker and Cohen's kappa computed by the real R service.
"""

from typing import Any

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models import AuditLog
from tests.test_consensus import MakeUser, _join, _project
from tests.test_search_import import _import

RIS = "".join(
    f"TY  - JOUR\nTI  - FICTITIOUS screening record {i}\nAB  - Abstract {i}.\nPY  - 2020\nER  - \n"
    for i in range(1, 7)
)


async def _team(client: AsyncClient, make_user: MakeUser) -> tuple[Any, Any, Any, dict[str, Any]]:
    ana = await make_user("Ana")
    p = await _project(client, ana)
    bia, caio = await make_user("Bia"), await make_user("Caio")
    await _join(client, ana, bia, p["pid"], ["reviewer"])
    await _join(client, ana, caio, p["pid"], ["reviewer"])
    r = await _import(client, ana, p, "busca.ris", RIS.encode())
    assert r.status_code == 201
    return ana, bia, caio, p


async def _queue(client: AsyncClient, user: Any, p: dict[str, Any], **params: Any) -> Any:
    r = await client.get(f"{p['base']}/screening/queue", headers=user.headers, params=params)
    assert r.status_code == 200, r.text
    return r.json()


async def _decide(
    client: AsyncClient, user: Any, p: dict[str, Any], ref: str, decision: str
) -> Any:
    return await client.post(
        f"{p['base']}/screening/references/{ref}/decision",
        headers=user.headers,
        json={"decision": decision},
    )


async def test_double_screening_conflict_rule_and_resolution(
    client: AsyncClient, make_user: MakeUser
) -> None:
    ana, bia, caio, p = await _team(client, make_user)
    refs = [i["reference"]["id"] for i in (await _queue(client, bia, p))["items"]]
    assert len(refs) == 6
    plan = [
        ("include", "include"),  # passes
        ("exclude", "exclude"),  # leaves
        ("include", "exclude"),  # conflict
        ("include", "maybe"),  # conflict: any "maybe"
        ("maybe", "maybe"),  # conflict
    ]
    for ref, (b, c) in zip(refs, plan, strict=False):
        assert (await _decide(client, bia, p, ref, b)).status_code == 201
        assert (await _decide(client, caio, p, ref, c)).status_code == 201
    counts = (await client.get(f"{p['base']}/screening/counts", headers=ana.headers)).json()
    assert counts["include"] == 1 and counts["exclude"] == 1
    assert counts["conflict"] == 3 and counts["pending"] == 1
    conflicts = await _queue(client, ana, p, view="conflicts")
    assert conflicts["total"] == 3
    url = f"{p['base']}/screening/references/{refs[2]}/resolution"
    body = {"decision": "include", "reason": "Discussed: meets criteria"}
    assert (await client.post(url, headers=bia.headers, json=body)).status_code == 403
    assert (await client.post(url, headers=ana.headers, json=body)).json() == {
        "status": "resolved_include"
    }
    again = await client.post(url, headers=ana.headers, json=body)
    assert again.json()["code"] == "screening.not_a_conflict"
    counts = (await client.get(f"{p['base']}/screening/counts", headers=ana.headers)).json()
    assert counts["conflict"] == 2 and counts["resolved"] == 1 and counts["include"] == 2
    assert (await client.delete(url, headers=ana.headers)).status_code == 204
    counts = (await client.get(f"{p['base']}/screening/counts", headers=ana.headers)).json()
    assert counts["conflict"] == 3


async def test_blinding_hides_other_reviewers_also_through_the_api(
    client: AsyncClient, make_user: MakeUser
) -> None:
    ana, bia, caio, p = await _team(client, make_user)
    ref = (await _queue(client, bia, p))["items"][0]["reference"]["id"]
    await _decide(client, bia, p, ref, "include")
    await _decide(client, caio, p, ref, "exclude")
    item = next(i for i in (await _queue(client, caio, p, view="done"))["items"])
    assert item["my_decision"] == "exclude" and item["others"] == [] and item["status"] is None
    hist = (
        await client.get(f"{p['base']}/screening/references/{ref}/history", headers=caio.headers)
    ).json()
    assert [h["decision"] for h in hist] == ["exclude"]
    counts = (await client.get(f"{p['base']}/screening/counts", headers=caio.headers)).json()
    assert counts["conflict"] is None
    assert (
        await client.get(
            f"{p['base']}/screening/queue", headers=caio.headers, params={"view": "conflicts"}
        )
    ).status_code == 403
    # The admin sees everything, and reveals by turning blinding off.
    item = (await _queue(client, ana, p, view="all"))["items"][0]
    assert item["status"] == "conflict" and len(item["others"]) == 2
    r = await client.put(
        f"{p['base']}/screening/settings", headers=ana.headers, json={"blind": False}
    )
    assert r.json()["blind"] is False
    item = next(i for i in (await _queue(client, caio, p, view="done"))["items"])
    assert item["others"][0]["decision"] == "include" and item["status"] == "conflict"


async def test_undo_brings_the_previous_decision_back_and_is_audited(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession
) -> None:
    _, bia, _, p = await _team(client, make_user)
    first, second = [i["reference"]["id"] for i in (await _queue(client, bia, p))["items"][:2]]
    await _decide(client, bia, p, first, "include")
    await _decide(client, bia, p, first, "exclude")  # changes her mind
    await _decide(client, bia, p, second, "maybe")
    undo = f"{p['base']}/screening/undo"
    r = (await client.post(undo, headers=bia.headers)).json()
    assert r["reference_id"] == second and r["decision"] == "none"
    r = (await client.post(undo, headers=bia.headers)).json()
    assert r["reference_id"] == first and r["decision"] == "include"
    hist = (
        await client.get(f"{p['base']}/screening/references/{first}/history", headers=bia.headers)
    ).json()
    assert [(h["decision"], h["current"], h["undone"]) for h in hist] == [
        ("include", True, False),
        ("exclude", False, True),
    ]
    rows = await session.scalars(
        select(AuditLog).where(
            AuditLog.entity == "screening_decisions", AuditLog.action == "update"
        )
    )
    assert rows.first() is not None
    await client.post(undo, headers=bia.headers)
    r = await client.post(undo, headers=bia.headers)
    assert r.json()["code"] == "screening.nothing_to_undo"


async def test_batches_useful_marker_roles_and_keywords(
    client: AsyncClient, make_user: MakeUser
) -> None:
    ana, bia, caio, p = await _team(client, make_user)
    base = f"{p['base']}/screening"
    r = await client.post(
        f"{base}/assignments", headers=ana.headers, json={"user_id": bia.id, "count": 2}
    )
    assert r.json()["assigned"] == 2
    assert (
        await client.post(
            f"{base}/assignments", headers=bia.headers, json={"user_id": bia.id, "count": 1}
        )
    ).status_code == 403
    todo_caio = await _queue(client, caio, p)
    assert todo_caio["total"] == 4  # the two in Bia's batch are not his to decide
    batch_ref = (await _queue(client, bia, p))["items"][0]["reference"]["id"]
    r = await _decide(client, caio, p, batch_ref, "include")
    assert r.json()["code"] == "screening.not_assigned"
    summary = (await client.get(f"{base}/assignments", headers=ana.headers)).json()
    assert summary[0]["user_name"] == "Bia" and summary[0]["decided"] == 0
    assert (
        await client.delete(f"{base}/assignments/{bia.id}", headers=ana.headers)
    ).status_code == 204
    assert (await _queue(client, caio, p))["total"] == 6

    reader = await make_user()
    await _join(client, ana, reader, p["pid"], ["reader"])
    assert (await _decide(client, reader, p, batch_ref, "include")).status_code == 403
    r = await client.put(
        f"{base}/references/{batch_ref}/useful", headers=bia.headers, json={"useful": True}
    )
    assert r.json() == {"useful_as_reference": True}
    item = next(
        i
        for i in (await _queue(client, ana, p, view="all"))["items"]
        if i["reference"]["id"] == batch_ref
    )
    assert item["useful_as_reference"] is True

    body = {"include_keywords": [" cohort ", "cohort", "children"], "exclude_keywords": ["rat"]}
    r = await client.put(f"{base}/settings", headers=ana.headers, json=body)
    assert r.json()["include_keywords"] == ["children", "cohort"] and r.json()["blind"] is True
    assert (await client.put(f"{base}/settings", headers=bia.headers, json=body)).status_code == 403
    assert (await _queue(client, bia, p, q="record 3"))["total"] == 1


async def test_kappa_between_reviewers_comes_from_r(
    client: AsyncClient, make_user: MakeUser
) -> None:
    ana, bia, caio, p = await _team(client, make_user)
    refs = [i["reference"]["id"] for i in (await _queue(client, bia, p))["items"]]
    for ref, b, c in zip(
        refs,
        ["include", "exclude", "include", "exclude"],
        ["include", "exclude", "exclude", "exclude"],
        strict=False,
    ):
        await _decide(client, bia, p, ref, b)
        await _decide(client, caio, p, ref, c)
    out = (await client.get(f"{p['base']}/screening/agreement", headers=ana.headers)).json()
    assert len(out) == 1 and out[0]["items"] == 4
    assert out[0]["agreement_percent"] == 75
    assert out[0]["kappa"] is not None and 0 < out[0]["kappa"] < 1
