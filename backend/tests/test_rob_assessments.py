"""Individual risk-of-bias assessments: target, blinding, suggestions and the group's rule."""

from typing import Any

from httpx import AsyncClient

from tests.conftest import LoggedUser
from tests.test_consensus import MakeUser, _join


async def _project(client: AsyncClient, ana: LoggedUser) -> dict[str, Any]:
    pid = (await client.post("/api/v1/projects", json={"title": "P"}, headers=ana.headers)).json()[
        "id"
    ]
    base = f"/api/v1/projects/{pid}"
    outcome = (
        await client.post(
            f"{base}/outcomes",
            json={"name": "QI", "type": "continuous", "timepoints": ["5 anos", "10 anos"]},
            headers=ana.headers,
        )
    ).json()
    studies = {}
    for label, design in (("Coorte 2020", "cohort_retrospective"), ("Ensaio 2019", "rct")):
        studies[design] = (
            await client.post(
                f"{base}/studies",
                json={"label": label, "design": design, "reference": {"title": label}},
                headers=ana.headers,
            )
        ).json()["id"]
    rob = f"{base}/rob"
    tools = {}
    for key in ("jbi_cohort", "rob2", "nos_cohort", "generic"):
        tools[key] = (
            await client.post(f"{rob}/tools", json={"template_key": key}, headers=ana.headers)
        ).json()
    return {
        "pid": pid,
        "base": base,
        "rob": rob,
        "outcome": outcome["id"],
        "studies": studies,
        "tools": tools,
    }


async def _confirm(
    client: AsyncClient, ana: LoggedUser, p: dict[str, Any], design: str, key: str
) -> None:
    r = await client.put(
        f"{p['rob']}/studies/{p['studies'][design]}/tool",
        json={"tool_id": p["tools"][key]["id"]},
        headers=ana.headers,
    )
    assert r.status_code == 200, r.text


async def _start(
    client: AsyncClient, user: LoggedUser, p: dict[str, Any], design: str, **body: Any
) -> Any:
    return await client.post(
        f"{p['rob']}/studies/{p['studies'][design]}/assessments", json=body, headers=user.headers
    )


async def _answers(
    client: AsyncClient, user: LoggedUser, p: dict[str, Any], aid: str, items: list[dict[str, Any]]
) -> Any:
    return await client.put(
        f"{p['rob']}/assessments/{aid}/answers", json={"answers": items}, headers=user.headers
    )


async def _judge(
    client: AsyncClient, user: LoggedUser, p: dict[str, Any], aid: str, **body: Any
) -> Any:
    return await client.put(
        f"{p['rob']}/assessments/{aid}/judgement", json=body, headers=user.headers
    )


async def test_start_needs_a_confirmed_instrument_and_is_blind(
    client: AsyncClient, make_user: MakeUser
) -> None:
    ana, bia, caio, dani, leo = [await make_user(n) for n in ("Ana", "Bia", "Caio", "Dani", "Leo")]
    p = await _project(client, ana)
    for user in (bia, caio, dani):
        await _join(client, ana, user, p["pid"], ["reviewer"])
    await _join(client, ana, leo, p["pid"], ["reader"])

    r = await _start(client, bia, p, "cohort_retrospective")
    assert r.json()["code"] == "rob.no_tool_confirmed"
    await _confirm(client, ana, p, "cohort_retrospective", "jbi_cohort")
    assert (await _start(client, leo, p, "cohort_retrospective")).status_code == 403

    mine = (await _start(client, bia, p, "cohort_retrospective")).json()
    assert mine["kind"] == "individual" and mine["status"] == "draft"
    assert mine["template_version"] == "2025"
    assert [t["outcome_name"] for t in mine["targets"]] == ["QI"]
    again = (await _start(client, bia, p, "cohort_retrospective")).json()
    assert again["id"] == mine["id"]  # one assessment per reviewer
    other = (await _start(client, caio, p, "cohort_retrospective")).json()
    r = await _start(client, dani, p, "cohort_retrospective")
    assert r.json()["code"] == "rob.enough_reviewers"

    # Blind: Bia neither sees nor finds Caio's assessment; the admin sees both.
    assert (
        await client.get(f"{p['rob']}/assessments/{other['id']}", headers=bia.headers)
    ).status_code == 404
    url = f"{p['rob']}/studies/{p['studies']['cohort_retrospective']}/assessments"
    assert [a["id"] for a in (await client.get(url, headers=bia.headers)).json()] == [mine["id"]]
    assert len((await client.get(url, headers=ana.headers)).json()) == 2
    # Nobody edits someone else's assessment.
    r = await _answers(
        client, bia, p, other["id"], [{"question_key": "selection.1", "answer": "Y"}]
    )
    assert r.status_code == 404


async def test_rob2_suggests_judgements_and_disagreeing_needs_a_reason(
    client: AsyncClient, make_user: MakeUser
) -> None:
    ana, bia = await make_user("Ana"), await make_user("Bia")
    p = await _project(client, ana)
    await _join(client, ana, bia, p["pid"], ["reviewer"])
    await _confirm(client, ana, p, "rct", "rob2")

    r = await _start(client, bia, p, "rct")
    assert r.json()["code"] == "rob.result_required"
    r = await _start(client, bia, p, "rct", outcome_id=p["outcome"], timepoint="20 anos")
    assert r.json()["code"] == "rob.unknown_result"
    a = (await _start(client, bia, p, "rct", outcome_id=p["outcome"], timepoint="5 anos")).json()
    aid = a["id"]
    assert "variant:d2" in a["missing"]

    # Domain 1: 1.2 Y, 1.1 Y, 1.3 N -> suggested Low (cribsheet p. 6)
    a = (
        await _answers(
            client,
            bia,
            p,
            aid,
            [
                {"question_key": "d1.1.1", "answer": "Y"},
                {"question_key": "d1.1.2", "answer": "Y"},
                {"question_key": "d1.1.3", "answer": "N", "justification": "Tabela 1 equilibrada"},
            ],
        )
    ).json()
    d1 = next(d for d in a["domains"] if d["domain_key"] == "d1")
    assert d1["suggested"] == "low"
    r = await _answers(client, bia, p, aid, [{"question_key": "d1.1.1", "answer": "WY"}])
    assert r.json()["code"] == "rob.invalid_answer"

    # Domain 2 asks the variant first; then skip rules show only what applies.
    r = await client.put(
        f"{p['rob']}/assessments/{aid}/variants",
        json={"variants": {"d2": "S"}},
        headers=bia.headers,
    )
    a = r.json()
    d2 = next(d for d in a["domains"] if d["domain_key"] == "d2")
    assert d2["variant"] == "S" and d2["asked"] == ["S2.1", "S2.2", "S2.6"]
    a = (
        await _answers(
            client,
            bia,
            p,
            aid,
            [
                {"question_key": "d2.S2.1", "answer": "N"},
                {"question_key": "d2.S2.2", "answer": "N"},
                {"question_key": "d2.S2.6", "answer": "Y"},
            ],
        )
    ).json()
    assert next(d for d in a["domains"] if d["domain_key"] == "d2")["suggested"] == "low"

    # Disagreeing with the suggestion is allowed, but needs a justification.
    a = (await _judge(client, bia, p, aid, domain_key="d1", final="some_concerns")).json()
    assert "justification:d1" in a["missing"]
    a = (
        await _judge(
            client,
            bia,
            p,
            aid,
            domain_key="d1",
            final="some_concerns",
            justification="Sigilo da alocação pouco claro",
        )
    ).json()
    assert "justification:d1" not in a["missing"]
    r = await _judge(client, bia, p, aid, domain_key="d1", final="moderate")
    assert r.json()["code"] == "rob.invalid_judgement"

    # Finish the other domains with the suggestions and submit.
    rest = [
        ("d3.3.1", "Y"),
        ("d4.4.1", "N"),
        ("d4.4.2", "N"),
        ("d4.4.3", "N"),
        ("d5.5.1", "Y"),
        ("d5.5.2", "N"),
        ("d5.5.3", "N"),
    ]
    a = (
        await _answers(client, bia, p, aid, [{"question_key": k, "answer": v} for k, v in rest])
    ).json()
    for d in a["domains"]:
        if d["domain_key"] != "d1":
            a = (
                await _judge(client, bia, p, aid, domain_key=d["domain_key"], final=d["suggested"])
            ).json()
    assert a["overall"]["suggested"] == "some_concerns"
    r = await client.post(f"{p['rob']}/assessments/{aid}/submit", headers=bia.headers)
    assert r.json()["code"] == "rob.incomplete"  # overall not judged yet
    await _judge(client, bia, p, aid, final="some_concerns", direction="towards_null")
    r = await client.post(f"{p['rob']}/assessments/{aid}/submit", headers=bia.headers)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "submitted" and r.json()["missing"] == []
    r = await _answers(client, bia, p, aid, [{"question_key": "d1.1.1", "answer": "N"}])
    assert r.json()["code"] == "rob.not_editable"


async def test_jbi_questions_per_outcome_and_the_group_rule(
    client: AsyncClient, make_user: MakeUser
) -> None:
    ana, bia = await make_user("Ana"), await make_user("Bia")
    p = await _project(client, ana)
    await _join(client, ana, bia, p["pid"], ["reviewer"])
    await _confirm(client, ana, p, "cohort_retrospective", "jbi_cohort")
    a = (await _start(client, bia, p, "cohort_retrospective")).json()
    aid, outcome = a["id"], p["outcome"]

    # Question 5 is appraised per outcome, question 9 per result (outcome + time point).
    r = await _answers(client, bia, p, aid, [{"question_key": "confounding.5", "answer": "Y"}])
    assert r.json()["code"] == "rob.wrong_target"
    r = await _answers(
        client, bia, p, aid, [{"question_key": "retention.9", "outcome_id": outcome, "answer": "Y"}]
    )
    assert r.json()["code"] == "rob.wrong_target"
    study_level = ["selection.1", "exposure.2", "exposure.3", "confounding.4"]
    items = [{"question_key": k, "answer": "Y"} for k in study_level]
    items += [
        {"question_key": k, "outcome_id": outcome, "answer": "Y"}
        for k in ("confounding.5", "temporal.6", "outcome.7", "outcome.8")
    ]
    items += [
        {
            "question_key": k,
            "outcome_id": outcome,
            "timepoint": t,
            "answer": "N" if k == "retention.9" else "Y",
        }
        for k in ("retention.9", "retention.10", "statistical.11")
        for t in ("5 anos", "10 anos")
    ]
    a = (await _answers(client, bia, p, aid, items)).json()
    assert [m for m in a["missing"] if m.startswith("answer:")] == []
    # No domain judgements in JBI, and no rule yet: the overall judgement is free.
    assert a["domains"][0]["suggested"] is None
    assert a["overall"]["suggested"] is None
    assert a["overall"]["levels"] == ["low", "moderate", "high"]
    r = await _judge(client, bia, p, aid, domain_key="selection", final="low")
    assert r.json()["code"] == "rob.no_domain_judgement"

    # The group defines a rule: 2 or more N/U anywhere -> high; otherwise low.
    tool = p["tools"]["jbi_cohort"]
    rule = {
        "levels": ["low", "high"],
        "cases": [{"then": "high", "count": {"answers": ["N", "U"], "at_least": 2}}],
        "else": "low",
    }
    r = await client.put(
        f"{p['rob']}/tools/{tool['id']}/overall-rule",
        json={"version": tool["version"], "rule": rule},
        headers=bia.headers,
    )
    assert r.status_code == 403
    r = await client.put(
        f"{p['rob']}/tools/{tool['id']}/overall-rule",
        json={"version": tool["version"], "rule": rule},
        headers=ana.headers,
    )
    assert r.status_code == 200, r.text
    a = (await client.get(f"{p['rob']}/assessments/{aid}", headers=bia.headers)).json()
    assert a["overall"]["suggested"] == "high"  # question 9 was "No" at both time points
    assert a["overall"]["levels"] == ["low", "high"]

    bad = {
        "levels": ["low", "high"],
        "cases": [{"then": "medium", "count": {"answers": ["N"], "at_least": 1}}],
        "else": "low",
    }
    tool = r.json()
    r = await client.put(
        f"{p['rob']}/tools/{tool['id']}/overall-rule",
        json={"version": tool["version"], "rule": bad},
        headers=ana.headers,
    )
    assert r.json()["code"] == "rob.invalid_rule"
    rob2 = p["tools"]["rob2"]
    r = await client.put(
        f"{p['rob']}/tools/{rob2['id']}/overall-rule",
        json={"version": rob2["version"], "rule": rule},
        headers=ana.headers,
    )
    assert r.json()["code"] == "rob.has_official_rule"


async def test_newcastle_ottawa_rule_by_stars(client: AsyncClient, make_user: MakeUser) -> None:
    ana = await make_user("Ana")
    p = await _project(client, ana)
    await _confirm(client, ana, p, "cohort_retrospective", "nos_cohort")
    tool = p["tools"]["nos_cohort"]
    rule = {
        "levels": ["poor", "fair", "good"],
        "cases": [{"then": "good", "stars_at_least": 7}, {"then": "fair", "stars_at_least": 5}],
        "else": "poor",
    }
    r = await client.put(
        f"{p['rob']}/tools/{tool['id']}/overall-rule",
        json={"version": tool["version"], "rule": rule},
        headers=ana.headers,
    )
    assert r.status_code == 200, r.text
    aid = (await _start(client, ana, p, "cohort_retrospective")).json()["id"]
    stars = {
        "selection.1": "1",
        "selection.2": "1",
        "selection.3": "1",
        "selection.4": "0",
        "comparability.1": "2",
        "outcome.1": "1",
        "outcome.2": "1",
        "outcome.3": "0",
    }
    a = (
        await _answers(
            client, ana, p, aid, [{"question_key": k, "answer": v} for k, v in stars.items()]
        )
    ).json()
    assert a["overall"]["suggested"] == "good"  # 7 stars
    r = await _answers(client, ana, p, aid, [{"question_key": "comparability.1", "answer": "3"}])
    assert r.json()["code"] == "rob.invalid_answer"  # comparability gives at most 2 stars


async def test_instrument_cannot_change_once_assessed(
    client: AsyncClient, make_user: MakeUser
) -> None:
    ana = await make_user("Ana")
    p = await _project(client, ana)
    generic = p["tools"]["generic"]
    r = await client.put(
        f"{p['rob']}/tools/{generic['id']}/structure",
        json={"version": generic["version"], "domains": [{"name": "D", "questions": 2}]},
        headers=ana.headers,
    )
    generic = r.json()
    await _confirm(client, ana, p, "cohort_retrospective", "generic")
    await _start(client, ana, p, "cohort_retrospective")
    r = await client.put(
        f"{p['rob']}/tools/{generic['id']}/structure",
        json={"version": generic["version"], "domains": [{"name": "D", "questions": 3}]},
        headers=ana.headers,
    )
    assert r.json()["code"] == "rob.tool_in_use"
    r = await client.put(
        f"{p['rob']}/studies/{p['studies']['cohort_retrospective']}/tool",
        json={"tool_id": p["tools"]["jbi_cohort"]["id"]},
        headers=ana.headers,
    )
    assert r.json()["code"] == "rob.study_has_assessments"
