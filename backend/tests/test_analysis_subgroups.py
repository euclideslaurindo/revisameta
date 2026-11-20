"""Subgroup analysis through the API (stage 4 step 2), with the real R service.

Expected values come from stats-r/fixtures/subgroup.json (metafor, public dat.bcg).
"""

import math
import uuid
from typing import Any

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.extraction.models import ExtractionForm
from tests.test_analysis_assembly import TOL, Seeder
from tests.test_consensus import MakeUser, _project
from tests.test_stats_reference import _fixture

SUB = _fixture("subgroup.json")


async def _bcg(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession
) -> tuple[Any, dict[str, Any], str]:
    ana = await make_user("Ana")
    p = await _project(client, ana)
    outcome = (
        await client.post(
            f"{p['base']}/outcomes",
            headers=ana.headers,
            json={"name": "TB", "type": "dichotomous", "timepoints": ["5 anos"]},
        )
    ).json()["id"]
    await client.get(f"{p['base']}/extraction-form", headers=ana.headers)
    form = (
        await session.scalars(
            select(ExtractionForm).where(ExtractionForm.project_id == uuid.UUID(p["pid"]))
        )
    ).first()
    assert form is not None
    plan = (await client.get(f"{p['base']}/analysis-plan", headers=ana.headers)).json()
    await client.put(
        f"{p['base']}/analysis-plan",
        headers=ana.headers,
        json={
            "version": plan["version"],
            "subgroups": ["Alocação"],
            "comparison": {"group1_id": p["groups"][0], "group2_id": p["groups"][1]},
        },
    )
    seed = Seeder(session, p, form.id)
    case = SUB["cases"][0]
    d = case["request"]["data"]
    meta = _fixture()
    raw = next(c for c in meta["cases"] if c["name"] == "dat.bcg_RR_REML_knha")["request"]["data"]
    for i, label in enumerate(d["label"]):
        await seed.study(
            label,
            [
                (0, {"events": raw["ai"][i], "total": raw["n1i"][i]}),
                (1, {"events": raw["ci"][i], "total": raw["n2i"][i]}),
            ],
            outcome_id=outcome,
            cutoff=4 if i % 2 else 5,
            characteristics={"alocacao": d["group"][i]},
        )
    return ana, p, outcome


async def test_subgroups_by_a_form_field_match_metafor(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession
) -> None:
    ana, p, outcome = await _bcg(client, make_user, session)
    for case in SUB["cases"]:
        req = case["request"]
        r = await client.post(
            f"{p['base']}/analyses/subgroups",
            headers=ana.headers,
            json={
                "outcome_id": outcome,
                "timepoint": "5 anos",
                "measure": "RR",
                "method": req["method"],
                "test": req["test"],
                "variable": "characteristic",
                "key": "alocacao",
                "label": "Alocação",
            },
        )
        assert r.status_code == 200, r.text
        out = r.json()
        e = case["expected"]
        by_group = {g["group"]: g for g in out["result"]["subgroups"]}
        assert set(by_group) == set(e["groups"])
        for name, est, lb in zip(e["groups"], e["estimate"], e["ci_lb"], strict=True):
            assert math.isclose(by_group[name]["estimate"], est, abs_tol=TOL), (case["name"], name)
            assert math.isclose(by_group[name]["ci_lb"], lb, abs_tol=TOL)
        test = out["result"]["test"]
        assert math.isclose(test["q"], e["q"], abs_tol=TOL) and test["df"] == e["df"]
        assert math.isclose(test["p_value"], e["p_value"], abs_tol=TOL)
        assert out["planned"] is True and out["left_out"] == []


async def test_subgroups_by_cutoff_and_missing_values(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession
) -> None:
    ana, p, outcome = await _bcg(client, make_user, session)
    url = f"{p['base']}/analyses/subgroups"
    body = {"outcome_id": outcome, "timepoint": "5 anos", "measure": "RR"}
    out = (await client.post(url, headers=ana.headers, json={**body, "variable": "cutoff"})).json()
    assert {g["group"] for g in out["result"]["subgroups"]} == {"4", "5"}
    assert out["planned"] is False
    r = await client.post(url, headers=ana.headers, json={**body, "variable": "characteristic"})
    assert r.json()["code"] == "analysis.subgroup_key_required"
    # A field nobody filled in leaves every study out: there are no two subgroups.
    r = await client.post(
        url, headers=ana.headers, json={**body, "variable": "characteristic", "key": "pais"}
    )
    assert r.json()["code"] == "analysis.subgroup_needs_two"
