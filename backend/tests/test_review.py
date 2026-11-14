"""Final review and extraction lock (docs/validacao.md 11.2, block F of 7.5.1)."""

from typing import Any

from httpx import AsyncClient

from tests.conftest import FakeR, LoggedUser
from tests.test_consensus import (
    MakeUser,
    _comparison,
    _divergent,
    _extract,
    _join,
    _project,
)


async def _review(client: AsyncClient, user: LoggedUser, p: dict[str, Any]) -> Any:
    r = await client.get(f"{p['base']}/extraction-review", headers=user.headers)
    assert r.status_code == 200, r.text
    return r.json()


async def _checked_consensus(
    client: AsyncClient, admin: LoggedUser, extractors: tuple[LoggedUser, ...], p: dict[str, Any]
) -> str:
    """Two extractions (SD differs), divergence settled with B, direction confirmed, submitted."""
    await _extract(client, extractors[0], p, sd="11.2")
    await _extract(client, extractors[1], p, sd="11.3")
    sbase = f"{p['base']}/studies/{p['study']}"
    consensus = (await client.post(f"{sbase}/consensus", headers=admin.headers)).json()
    [item] = _divergent((await _comparison(client, admin, p)).json()).values()
    await client.post(
        f"{sbase}/decisions", json={"key": item["key"], "choice": "b"}, headers=admin.headers
    )
    cb = f"{p['base']}/extractions/{consensus['id']}"
    r = await client.post(
        f"{cb}/direction/confirm",
        json={"outcome_id": p["outcome"], "timepoint": "5 anos"},
        headers=admin.headers,
    )
    assert r.status_code == 200, r.text
    r = await client.post(f"{cb}/submit", headers=admin.headers)
    assert r.status_code == 200, r.text
    return str(consensus["id"])


async def test_review_lists_what_blocks_the_lock(
    client: AsyncClient, make_user: MakeUser, fake_r: FakeR
) -> None:
    ana, bia, caio = await make_user("Ana"), await make_user("Bia"), await make_user("Caio")
    p = await _project(client, ana)
    for user in (bia, caio):
        await _join(client, ana, user, p["pid"], ["extractor"])

    review = await _review(client, ana, p)
    assert review["total"] == 1 and review["ready"] == 0 and review["can_lock"] is False
    assert review["studies"][0]["blockers"] == ["review.no_consensus"]

    await _extract(client, bia, p, sd="11.2")
    await _extract(client, caio, p, sd="11.2")
    await client.post(f"{p['base']}/studies/{p['study']}/consensus", headers=ana.headers)
    study = (await _review(client, ana, p))["studies"][0]
    # Draft consensus, and the direction sentence was never confirmed in it.
    assert study["blockers"] == ["review.consensus_draft", "review.open_alerts"]
    assert {a["code"] for a in study["open_alerts"]} == {"extraction.alert.direction_unconfirmed"}

    r = await client.post(f"{p['base']}/extraction-review/lock", headers=ana.headers)
    assert r.status_code == 409
    assert r.json()["code"] == "review.not_ready"


async def test_review_shows_every_number_and_how_it_was_checked(
    client: AsyncClient, make_user: MakeUser, fake_r: FakeR
) -> None:
    ana, bia, caio = await make_user("Ana"), await make_user("Bia"), await make_user("Caio")
    p = await _project(client, ana)
    for user in (bia, caio):
        await _join(client, ana, user, p["pid"], ["extractor"])
    await _checked_consensus(client, ana, (bia, caio), p)

    review = await _review(client, ana, p)
    assert review["can_lock"] is True
    study = review["studies"][0]
    assert study["blockers"] == []
    assert study["consensus_status"] == "submitted"
    assert study["checked_by"] == "Ana"
    assert sorted(study["extractors"]) == ["Bia", "Caio"]
    early = next(r for r in study["rows"] if r["arm_label"] == "Precoce")
    assert early["dispersion_type"] == "sd"
    assert early["source_location"] == "p. 3"
    checks = {n["field"]: (n["value"], n["check"]) for n in early["numbers"]}
    assert checks["mean"] == ("92.5", {"status": "agreed", "choice": None, "by": None})
    assert checks["sd"][0] == "11.3"
    assert checks["sd"][1] == {"status": "decided", "choice": "b", "by": "Ana"}
    assert {a["check"]["status"] for a in study["arms"]} == {"agreed"}


def test_a_number_nobody_reported_is_not_shown_as_checked() -> None:
    from app.modules.extraction.review import _check

    assert _check("arm|g:1|n", None, None, {}, {}, "Ana").status == "empty"
    assert _check("arm|g:1|n", 30, None, {}, {}, "Ana").status == "single"


async def test_lock_freezes_extraction_and_unlock_needs_a_reason(
    client: AsyncClient, make_user: MakeUser, fake_r: FakeR
) -> None:
    ana, bia, caio = await make_user("Ana"), await make_user("Bia"), await make_user("Caio")
    p = await _project(client, ana)
    for user in (bia, caio):
        await _join(client, ana, user, p["pid"], ["extractor"])
    consensus_id = await _checked_consensus(client, ana, (bia, caio), p)
    cb = f"{p['base']}/extractions/{consensus_id}"

    # Extractors may see the review but not lock it.
    assert (await _review(client, bia, p))["can_lock"] is True
    r = await client.post(f"{p['base']}/extraction-review/lock", headers=bia.headers)
    assert r.status_code == 403

    r = await client.post(f"{p['base']}/extraction-review/lock", headers=ana.headers)
    assert r.status_code == 200, r.text
    review = r.json()
    assert review["locked"] is True
    assert review["studies"][0]["consensus_status"] == "locked"
    assert [e["action"] for e in review["history"]] == ["lock"]

    # Nothing in the stage can change while it is locked.
    form = (await client.get(f"{p['base']}/extraction-form", headers=ana.headers)).json()
    writes = [
        await client.post(
            f"{cb}/reopen", json={"justification": "corrigir n"}, headers=ana.headers
        ),
        await client.put(
            f"{p['base']}/extraction-form",
            json={"version": form["version"], "schema": form["schema"]},
            headers=ana.headers,
        ),
        await client.post(f"{p['base']}/studies/{p['study']}/extractions", headers=ana.headers),
    ]
    assert [w.json()["code"] for w in writes] == ["stage.locked"] * 3

    r = await client.post(
        f"{p['base']}/extraction-review/unlock", json={"justification": ""}, headers=ana.headers
    )
    assert r.status_code == 422
    r = await client.post(
        f"{p['base']}/extraction-review/unlock",
        json={"justification": "Revisor do congresso pediu para conferir o n"},
        headers=ana.headers,
    )
    assert r.status_code == 200
    review = r.json()
    assert review["locked"] is False
    assert review["studies"][0]["consensus_status"] == "submitted"
    assert review["history"][0]["action"] == "unlock"
    assert review["history"][0]["justification"].startswith("Revisor")

    # A submitted consensus can be reopened (justified) to correct a number.
    r = await client.post(f"{cb}/reopen", json={"justification": "n do grupo"}, headers=ana.headers)
    assert r.status_code == 204
    detail = (await client.get(cb, headers=ana.headers)).json()
    assert detail["status"] == "draft"
    review = await _review(client, ana, p)
    assert review["history"][0]["action"] == "reopen"
    assert review["can_lock"] is False


async def test_single_extraction_is_checked_by_whoever_submits_the_consensus(
    client: AsyncClient, make_user: MakeUser, fake_r: FakeR
) -> None:
    ana, bia = await make_user("Ana"), await make_user("Bia")
    p = await _project(client, ana)
    project = (await client.get(f"/api/v1/projects/{p['pid']}", headers=ana.headers)).json()
    await client.patch(
        f"/api/v1/projects/{p['pid']}",
        json={"version": project["version"], "double_extraction": False},
        headers=ana.headers,
    )
    await _join(client, ana, bia, p["pid"], ["extractor"])
    await _extract(client, bia, p)
    consensus = next(
        e
        for e in (
            await client.get(f"{p['base']}/studies/{p['study']}/extractions", headers=ana.headers)
        ).json()
        if e["kind"] == "consensus"
    )
    cb = f"{p['base']}/extractions/{consensus['id']}"
    await client.post(
        f"{cb}/direction/confirm",
        json={"outcome_id": p["outcome"], "timepoint": "5 anos"},
        headers=ana.headers,
    )
    assert (await client.post(f"{cb}/submit", headers=ana.headers)).status_code == 200
    study = (await _review(client, ana, p))["studies"][0]
    assert study["blockers"] == []
    assert {n["check"]["status"] for r in study["rows"] for n in r["numbers"]} == {"single"}
    assert study["rows"][0]["numbers"][0]["check"]["by"] == "Ana"
