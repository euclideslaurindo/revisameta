"""Consolidated risk-of-bias table and plots (stage 2 step 4).

R is replaced by a fake transport: these tests check the table the backend builds and
what it sends to R. The plots themselves are tested in stats-r/tests/testthat.
"""

from typing import Any

from httpx import AsyncClient

from tests.conftest import FakeR
from tests.test_consensus import MakeUser
from tests.test_rob_consensus import STARS_A, _assess, _team, _url


async def _consensus(client: AsyncClient, ana: Any, p: dict[str, Any], submit: bool) -> str:
    created = (await client.post(f"{_url(p)}/consensus", json={}, headers=ana.headers)).json()
    cid = created["consensus"]["id"]
    for item in created["items"]:
        if not item["agree"]:
            await client.post(
                f"{p['rob']}/assessments/{cid}/decisions",
                json={"key": item["key"], "choice": "a"},
                headers=ana.headers,
            )
    if submit:
        r = await client.post(f"{p['rob']}/assessments/{cid}/submit", headers=ana.headers)
        assert r.status_code == 200, r.text
    return str(cid)


async def test_table_lists_only_submitted_consensus_and_says_who_is_missing(
    client: AsyncClient, make_user: MakeUser, fake_r: FakeR
) -> None:
    ana, bia, caio, p = await _team(client, make_user)
    tool_id = p["tools"]["nos_cohort"]["id"]
    url = f"{p['rob']}/table?tool_id={tool_id}"
    plot = {"tool_id": tool_id, "kind": "traffic_light", "format": "svg"}

    t = (await client.get(url, headers=bia.headers)).json()
    assert t["rows"] == []
    assert t["pending"][0]["reason"] == "no_assessment"
    assert t["needs_target"] is False
    assert [c["short"] for c in t["columns"]][:2] == ["Q1", "Q2"]
    # Newcastle-Ottawa answers are star counts out of each item's maximum.
    assert "stars_2_of_2" in t["levels"] and "stars_1_of_1" in t["levels"]

    await _assess(client, bia, p, STARS_A, "low")
    t = (await client.get(url, headers=bia.headers)).json()
    assert t["pending"][0]["reason"] == "in_progress"
    await _assess(client, caio, p, {**STARS_A, "outcome.3": "1"}, "moderate")
    await _consensus(client, ana, p, submit=False)
    t = (await client.get(url, headers=bia.headers)).json()
    assert t["pending"][0]["reason"] == "consensus_pending"
    r = await client.post(f"{p['rob']}/plots", json=plot, headers=bia.headers)
    assert r.json()["code"] == "rob.nothing_to_plot"

    cid = (await client.get(f"{_url(p)}/comparisons", headers=ana.headers)).json()[0]["consensus"][
        "id"
    ]
    assert (
        await client.post(f"{p['rob']}/assessments/{cid}/submit", headers=ana.headers)
    ).status_code == 200
    t = (await client.get(url, headers=bia.headers)).json()
    assert t["pending"] == []
    row = t["rows"][0]
    assert row["assessment_id"] == cid and row["kind"] == "consensus"
    assert row["overall"] == "low"  # reviewer A's, chosen at consensus
    assert row["values"]["comparability.1"] == "stars_2_of_2"
    assert row["values"]["selection.4"] == "stars_0_of_1"

    r = await client.post(f"{p['rob']}/plots", json={**plot, "lang": "en"}, headers=bia.headers)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("image/svg+xml")
    assert "risk-of-bias-traffic-light" in r.headers["content-disposition"]
    assert r.content == b"<svg/>"
    spec = fake_r.calls[-1]
    assert spec["kind"] == "traffic_light" and spec["texts"]["overall"] == "Overall"
    assert spec["studies"][0]["values"]["comparability.1"] == "stars_2_of_2"
    labels = {lv["key"]: lv["label"] for lv in spec["levels"]}
    # Only the levels used are sent, with labels in the output language.
    assert labels["stars_2_of_2"] == "2 of 2 star(s)" and labels["low"] == "Low"
    assert "high" not in labels


async def test_per_result_instruments_need_a_result_and_missing_studies_need_consent(
    client: AsyncClient, make_user: MakeUser, fake_r: FakeR
) -> None:
    ana, bia, caio, p = await _team(client, make_user)
    tool_id = p["tools"]["rob2"]["id"]
    r = await client.get(f"{p['rob']}/table?tool_id={tool_id}", headers=bia.headers)
    assert r.json()["code"] == "rob.result_required"
    r = await client.get(
        f"{p['rob']}/table?tool_id={tool_id}&outcome_id={p['outcome']}&timepoint=20 anos",
        headers=bia.headers,
    )
    assert r.json()["code"] == "rob.unknown_result"

    # A second NOS study still waiting keeps the plot from being drawn silently.
    nos = p["tools"]["nos_cohort"]["id"]
    other = (
        await client.post(
            f"{p['base']}/studies",
            json={
                "label": "Coorte 2022",
                "design": "cohort_prospective",
                "reference": {"title": "X"},
            },
            headers=ana.headers,
        )
    ).json()["id"]
    await client.put(f"{p['rob']}/studies/{other}/tool", json={"tool_id": nos}, headers=ana.headers)
    await _assess(client, bia, p, STARS_A, "low")
    await _assess(client, caio, p, STARS_A, "low")
    await _consensus(client, ana, p, submit=True)
    plot = {"tool_id": nos, "kind": "summary", "format": "png"}
    r = await client.post(f"{p['rob']}/plots", json=plot, headers=bia.headers)
    assert r.json()["code"] == "rob.plot_missing_studies"
    r = await client.post(
        f"{p['rob']}/plots", json={**plot, "acknowledge_missing": True}, headers=bia.headers
    )
    assert r.status_code == 200, r.text
    assert r.headers["x-left-out-studies"] == "1"
    assert "risco-de-vies-resumo" in r.headers["content-disposition"]

    fake_r.down = True
    r = await client.post(
        f"{p['rob']}/plots", json={**plot, "acknowledge_missing": True}, headers=bia.headers
    )
    assert r.json()["code"] == "error.stats_unavailable"
