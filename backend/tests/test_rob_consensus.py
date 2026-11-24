"""Risk-of-bias conflicts, consensus and agreement (stage 2 step 3).

R is replaced by a fake transport; the kappa values themselves are tested against irr
in stats-r/tests/testthat/test-kappa.R.
"""

import uuid
from typing import Any

from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.risk_of_bias.models import RobAssessment
from tests.conftest import FAKE_KAPPA, FakeR, LoggedUser
from tests.test_consensus import MakeUser, _join
from tests.test_rob_assessments import _answers, _confirm, _judge, _project, _start

STARS_A = {
    "selection.1": "1",
    "selection.2": "1",
    "selection.3": "1",
    "selection.4": "0",
    "comparability.1": "2",
    "outcome.1": "1",
    "outcome.2": "1",
    "outcome.3": "0",
}


async def _assess(
    client: AsyncClient,
    user: LoggedUser,
    p: dict[str, Any],
    stars: dict[str, str],
    overall: str,
    submit: bool = True,
) -> str:
    aid = (await _start(client, user, p, "cohort_retrospective")).json()["id"]
    await _answers(
        client, user, p, aid, [{"question_key": k, "answer": v} for k, v in stars.items()]
    )
    await _judge(client, user, p, aid, final=overall, justification="Conforme o artigo")
    if submit:
        r = await client.post(f"{p['rob']}/assessments/{aid}/submit", headers=user.headers)
        assert r.status_code == 200, r.text
    return str(aid)


async def _team(client: AsyncClient, make_user: MakeUser) -> tuple[Any, ...]:
    ana, bia, caio = await make_user("Ana"), await make_user("Bia"), await make_user("Caio")
    p = await _project(client, ana)
    for user in (bia, caio):
        await _join(client, ana, user, p["pid"], ["reviewer"])
    await _confirm(client, ana, p, "cohort_retrospective", "nos_cohort")
    return ana, bia, caio, p


def _url(p: dict[str, Any]) -> str:
    return f"{p['rob']}/studies/{p['studies']['cohort_retrospective']}"


async def test_conflicts_consensus_and_submission(
    client: AsyncClient, make_user: MakeUser, fake_r: FakeR
) -> None:
    ana, bia, caio, p = await _team(client, make_user)
    a_id = await _assess(client, bia, p, STARS_A, "low")
    # Caio has not submitted yet: no comparison values, no consensus.
    b_id = await _assess(
        client, caio, p, {**STARS_A, "selection.4": "1", "outcome.3": "1"}, "moderate", submit=False
    )
    cmp = (await client.get(f"{_url(p)}/comparisons", headers=ana.headers)).json()
    assert cmp[0]["submitted"] == 1 and cmp[0]["items"] == []
    r = await client.post(f"{_url(p)}/consensus", json={}, headers=ana.headers)
    assert r.json()["code"] == "rob.consensus_waiting"
    # Reviewers never see the comparison.
    r = await client.get(f"{_url(p)}/comparisons", headers=bia.headers)
    assert r.status_code == 403

    await client.post(f"{p['rob']}/assessments/{b_id}/submit", headers=caio.headers)
    cmp = (await client.get(f"{_url(p)}/comparisons", headers=ana.headers)).json()[0]
    assert {r["side"] for r in cmp["reviewers"]} == {"a", "b"}
    conflicts = {i["key"] for i in cmp["items"] if not i["agree"]}
    assert conflicts == {
        "answer|selection.4||",
        "answer|outcome.3||",
        "overall",
    }
    assert cmp["divergences"] == 3 and cmp["undecided"] == 3
    # Agreement comes from R: one code per compared item, A against B.
    assert cmp["agreement"]["kappa"] == FAKE_KAPPA["kappa"]
    sent = fake_r.calls[-1]
    assert len(sent["rater_a"]) == len(cmp["items"]) == 9
    assert sent["rater_a"][-1] == "low" and sent["rater_b"][-1] == "moderate"

    created = (await client.post(f"{_url(p)}/consensus", json={}, headers=ana.headers)).json()
    cid = created["consensus"]["id"]
    # The consensus starts from reviewer A.
    overall = next(i for i in created["items"] if i["key"] == "overall")
    assert overall["consensus_value"] == "low"
    r = await client.post(f"{_url(p)}/consensus", json={}, headers=ana.headers)
    assert r.json()["code"] == "rob.consensus_exists"

    decide = f"{p['rob']}/assessments/{cid}/decisions"
    r = await client.post(
        decide, json={"key": "answer|selection.1||", "choice": "a"}, headers=ana.headers
    )
    assert r.json()["code"] == "rob.not_a_conflict"
    r = await client.post(
        decide, json={"key": "overall", "choice": "consensus", "reason": "x"}, headers=ana.headers
    )
    assert r.json()["code"] == "rob.reason_required"
    r = await client.post(decide, json={"key": "overall", "choice": "b"}, headers=bia.headers)
    assert r.status_code == 403

    after = (
        await client.post(
            decide, json={"key": "answer|selection.4||", "choice": "b"}, headers=ana.headers
        )
    ).json()
    item = next(i for i in after["items"] if i["key"] == "answer|selection.4||")
    assert item["consensus_value"] == "1"
    assert item["decision"]["choice"] == "b" and item["decision"]["decided_by_name"] == "Ana"
    assert after["undecided"] == 2

    r = await client.post(f"{p['rob']}/assessments/{cid}/submit", headers=ana.headers)
    assert r.json()["code"] == "rob.undecided_conflicts"

    await client.post(
        decide, json={"key": "answer|outcome.3||", "choice": "a"}, headers=ana.headers
    )
    # The admin edits the consensus and justifies keeping a third value.
    await _judge(client, ana, p, cid, final="moderate", justification="Decidido em reunião")
    after = (
        await client.post(
            decide,
            json={"key": "overall", "choice": "consensus", "reason": "Decidido em reunião"},
            headers=ana.headers,
        )
    ).json()
    assert after["undecided"] == 0
    r = await client.post(f"{p['rob']}/assessments/{cid}/submit", headers=ana.headers)
    assert r.status_code == 200, r.text
    # Everyone in the project sees the submitted consensus; individual ones stay blind.
    seen = (await client.get(f"{_url(p)}/assessments", headers=bia.headers)).json()
    assert {a["id"] for a in seen} == {a_id, cid}


async def test_skipped_questions_are_not_conflicts(
    client: AsyncClient, make_user: MakeUser, fake_r: FakeR, session: AsyncSession
) -> None:
    """An answer left in a question the instrument skips never shows up as a conflict."""
    ana, bia, caio = await make_user("Ana"), await make_user("Bia"), await make_user("Caio")
    p = await _project(client, ana)
    for user in (bia, caio):
        await _join(client, ana, user, p["pid"], ["reviewer"])
    await _confirm(client, ana, p, "rct", "rob2")
    target = {"outcome_id": p["outcome"], "timepoint": "5 anos"}
    ids = []
    for user, stale in ((bia, "Y"), (caio, None)):
        aid = (await _start(client, user, p, "rct", **target)).json()["id"]
        await client.put(
            f"{p['rob']}/assessments/{aid}/variants",
            json={"variants": {"d2": "S"}},
            headers=user.headers,
        )
        # 2.1 and 2.2 = N: rule 2.3 is skipped. Bia had answered it before changing 2.1.
        items = [
            {"question_key": "d2.S2.1", "answer": "N"},
            {"question_key": "d2.S2.2", "answer": "N"},
        ]
        if stale:
            items.append({"question_key": "d2.S2.3", "answer": stale})
        r = await _answers(client, user, p, aid, items)
        assert r.status_code == 200, r.text
        ids.append(aid)
    # Completing every RoB 2 domain is covered elsewhere; mark both as submitted here.
    await session.execute(
        update(RobAssessment)
        .where(RobAssessment.id.in_([uuid.UUID(i) for i in ids]))
        .values(status="submitted")
    )
    await session.commit()
    url = f"{p['rob']}/studies/{p['studies']['rct']}/comparisons"
    cmp = (await client.get(url, headers=ana.headers)).json()[0]
    keys = {i["key"] for i in cmp["items"]}
    assert not any("S2.3" in k for k in keys)
    assert cmp["divergences"] == 0
    assert f"answer|d2.S2.1|{p['outcome']}|5 anos" not in keys  # per-result: no target keys
    assert "answer|d2.S2.1||" in keys and "variant|d2" in keys


async def test_comparison_works_when_r_is_down_and_project_agreement(
    client: AsyncClient, make_user: MakeUser, fake_r: FakeR
) -> None:
    ana, bia, caio, p = await _team(client, make_user)
    await _assess(client, bia, p, STARS_A, "low")
    await _assess(client, caio, p, STARS_A, "moderate")
    fake_r.down = True
    cmp = (await client.get(f"{_url(p)}/comparisons", headers=ana.headers)).json()[0]
    assert cmp["agreement"] is None and cmp["agreement_error"] == "error.stats_unavailable"
    assert cmp["divergences"] == 1
    fake_r.down = False
    agreement = (await client.get(f"{p['rob']}/agreement", headers=bia.headers)).json()
    assert agreement["pairs"] == 1
    # Only judgements count for the project agreement (here: the overall one).
    assert fake_r.calls[-1] == {"rater_a": ["low"], "rater_b": ["moderate"]}


async def test_single_reviewer_mode_starts_consensus_after_one_assessment(
    client: AsyncClient, make_user: MakeUser, fake_r: FakeR
) -> None:
    ana, bia, _caio, p = await _team(client, make_user)
    await _assess(client, bia, p, STARS_A, "low")
    r = await client.post(f"{_url(p)}/consensus", json={}, headers=ana.headers)
    assert r.json()["code"] == "rob.consensus_waiting"
    # Only the admin may change the rule.
    project = (await client.get(f"/api/v1/projects/{p['pid']}", headers=ana.headers)).json()
    r = await client.patch(
        f"/api/v1/projects/{p['pid']}",
        json={"version": project["version"], "double_rob": False},
        headers=bia.headers,
    )
    assert r.status_code == 403
    r = await client.patch(
        f"/api/v1/projects/{p['pid']}",
        json={"version": project["version"], "double_rob": False},
        headers=ana.headers,
    )
    assert r.status_code == 200 and r.json()["double_rob"] is False

    cmp = (await client.get(f"{_url(p)}/comparisons", headers=ana.headers)).json()[0]
    assert cmp["submitted"] == 1 and cmp["needed"] == 1
    review = (await client.get(f"{p['rob']}/review", headers=ana.headers)).json()
    assert review["studies"][0]["targets"][0]["state"] == "consensus_pending"
    created = (await client.post(f"{_url(p)}/consensus", json={}, headers=ana.headers)).json()
    cid = created["consensus"]["id"]
    # A person still checks and submits the consensus: nothing becomes final on its own.
    assert created["consensus"]["status"] == "draft"
    r = await client.post(f"{p['rob']}/assessments/{cid}/submit", headers=ana.headers)
    assert r.status_code == 200, r.text
