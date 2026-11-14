"""Risk-of-bias instruments: catalog, project copies, official wording and choice per study."""

import json
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.projects.models import Project
from app.modules.risk_of_bias.catalog import TEMPLATES_DIR, catalog
from tests.test_consensus import MakeUser, _join


def test_catalog_has_structure_and_never_the_official_wording() -> None:
    templates = catalog()
    assert {"jbi_cohort", "jbi_rct", "nos_cohort", "nos_case_control", "generic"} <= set(templates)
    # JBI cohort (2025): 11 questions; some are answered per outcome or per result.
    cohort = templates["jbi_cohort"]
    levels = [q.level for d in cohort.domains for q in d.questions]
    assert len(levels) == 11
    assert levels.count("study") == 4 and levels.count("outcome") == 4
    assert levels.count("result") == 3
    # Newcastle-Ottawa: comparability gives up to two stars.
    nos = templates["nos_cohort"]
    comparability = next(d for d in nos.domains if d.key == "comparability")
    assert nos.answer_sets[comparability.questions[0].answers] == ["0", "1", "2"]
    # Questions carry only key, answer set and level: no wording is shipped.
    for path in TEMPLATES_DIR.glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        for domain in data["domains"]:
            for question in domain["questions"]:
                assert set(question) == {"key", "answers", "level"}, path.name


async def _project(client: AsyncClient, admin: Any) -> dict[str, Any]:
    pid = (
        await client.post("/api/v1/projects", json={"title": "P"}, headers=admin.headers)
    ).json()["id"]
    base = f"/api/v1/projects/{pid}"
    studies = {}
    for label, design in (("Coorte 2020", "cohort_retrospective"), ("Ensaio 2019", "rct")):
        studies[design] = (
            await client.post(
                f"{base}/studies",
                json={"label": label, "design": design, "reference": {"title": label}},
                headers=admin.headers,
            )
        ).json()["id"]
    return {"pid": pid, "base": base, "rob": f"{base}/rob", "studies": studies}


async def _enable(client: AsyncClient, user: Any, p: dict[str, Any], key: str) -> Any:
    return await client.post(f"{p['rob']}/tools", json={"template_key": key}, headers=user.headers)


async def test_admin_enables_instruments_with_their_version(
    client: AsyncClient, make_user: MakeUser
) -> None:
    ana, bia = await make_user("Ana"), await make_user("Bia")
    p = await _project(client, ana)
    await _join(client, ana, bia, p["pid"], ["reviewer"])

    listed = (await client.get(f"{p['rob']}/catalog", headers=bia.headers)).json()
    cohort = next(i for i in listed if i["key"] == "jbi_cohort")
    assert cohort["version"] == "2025" and cohort["questions"] == 11
    assert "JBI Evid Synth. 2025" in cohort["citation"]

    r = await _enable(client, ana, p, "jbi_cohort")
    assert r.status_code == 201, r.text
    tool = r.json()
    assert tool["template_version"] == "2025"
    assert tool["texts_filled"] == 0 and tool["questions"] == 11
    assert (await _enable(client, ana, p, "jbi_cohort")).json()["code"] == "rob.already_enabled"
    assert (await _enable(client, ana, p, "nao_existe")).json()["code"] == "rob.unknown_template"
    assert (await _enable(client, bia, p, "nos_cohort")).status_code == 403


async def test_official_wording_is_pasted_by_the_admin(
    client: AsyncClient, make_user: MakeUser
) -> None:
    ana = await make_user("Ana")
    p = await _project(client, ana)
    tool = (await _enable(client, ana, p, "jbi_cohort")).json()
    url = f"{p['rob']}/tools/{tool['id']}/texts"
    r = await client.put(
        url,
        json={"version": tool["version"], "texts": {"selection.1": "  Texto colado pelo admin  "}},
        headers=ana.headers,
    )
    assert r.status_code == 200, r.text
    tool = r.json()
    assert tool["texts"] == {"selection.1": "Texto colado pelo admin"}
    assert tool["texts_filled"] == 1

    r = await client.put(
        url, json={"version": tool["version"], "texts": {"x.99": "?"}}, headers=ana.headers
    )
    assert r.json()["code"] == "rob.unknown_question"
    r = await client.put(url, json={"version": 1, "texts": {}}, headers=ana.headers)
    assert r.status_code == 409  # optimistic lock
    r = await client.put(
        url, json={"version": tool["version"], "texts": {"selection.1": ""}}, headers=ana.headers
    )
    assert r.json()["texts"] == {}


async def test_generic_instrument_gets_its_domains_from_the_group(
    client: AsyncClient, make_user: MakeUser
) -> None:
    ana = await make_user("Ana")
    p = await _project(client, ana)
    generic = (await _enable(client, ana, p, "generic")).json()
    r = await client.put(
        f"{p['rob']}/tools/{generic['id']}/structure",
        json={
            "version": generic["version"],
            "domains": [{"name": "Seleção", "questions": 2}, {"name": "Desfecho", "questions": 1}],
        },
        headers=ana.headers,
    )
    assert r.status_code == 200, r.text
    domains = r.json()["structure"]["domains"]
    assert [(d["key"], len(d["questions"])) for d in domains] == [("d1", 2), ("d2", 1)]
    assert r.json()["questions"] == 3

    cohort = (await _enable(client, ana, p, "jbi_cohort")).json()
    r = await client.put(
        f"{p['rob']}/tools/{cohort['id']}/structure",
        json={"version": cohort["version"], "domains": [{"name": "X", "questions": 1}]},
        headers=ana.headers,
    )
    assert r.json()["code"] == "rob.not_generic"


async def test_study_instrument_is_suggested_by_design_and_confirmed_by_admin(
    client: AsyncClient, make_user: MakeUser
) -> None:
    ana, bia = await make_user("Ana"), await make_user("Bia")
    p = await _project(client, ana)
    await _join(client, ana, bia, p["pid"], ["reviewer"])
    cohort_study, rct_study = p["studies"]["cohort_retrospective"], p["studies"]["rct"]

    r = await client.get(f"{p['rob']}/studies/{cohort_study}/tool", headers=bia.headers)
    assert r.json()["suggested_tool_id"] is None  # nothing enabled yet

    nos = (await _enable(client, ana, p, "nos_cohort")).json()
    jbi = (await _enable(client, ana, p, "jbi_cohort")).json()
    generic = (await _enable(client, ana, p, "generic")).json()
    r = (await client.get(f"{p['rob']}/studies/{cohort_study}/tool", headers=bia.headers)).json()
    assert r["suggested_tool_id"] == jbi["id"]  # JBI before NOS for cohorts
    assert r["confirmed"] is False
    # No instrument for trials enabled: the generic one is suggested.
    r = (await client.get(f"{p['rob']}/studies/{rct_study}/tool", headers=bia.headers)).json()
    assert r["suggested_tool_id"] == generic["id"]

    url = f"{p['rob']}/studies/{cohort_study}/tool"
    assert (
        await client.put(url, json={"tool_id": nos["id"]}, headers=bia.headers)
    ).status_code == 403
    r = await client.put(url, json={"tool_id": nos["id"]}, headers=ana.headers)
    assert r.json()["tool_id"] == nos["id"] and r.json()["confirmed"] is True


@pytest.mark.parametrize("stage", ["risk_of_bias"])
async def test_locked_stage_refuses_changes(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession, stage: str
) -> None:
    ana = await make_user("Ana")
    p = await _project(client, ana)
    await session.execute(
        update(Project).where(Project.id == p["pid"]).values(locked_stages=[stage])
    )
    await session.commit()
    r = await _enable(client, ana, p, "jbi_cohort")
    assert r.status_code == 409 and r.json()["code"] == "stage.locked"
