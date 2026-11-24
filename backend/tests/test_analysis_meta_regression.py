"""Meta-regression through the API (stage 8 step 1), with the real R service.

Expected values come from stats-r/fixtures/meta-regression.json (metafor, public
dat.bcg: absolute latitude and type of allocation as moderators).
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

MR = _fixture("meta-regression.json")


async def _bcg(client: AsyncClient, make_user: MakeUser, session: AsyncSession) -> Any:
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
            "comparison": {"group1_id": p["groups"][0], "group2_id": p["groups"][1]},
        },
    )
    seed = Seeder(session, p, form.id)
    d = MR["cases"][3]["request"]["data"]
    raw = next(c for c in _fixture()["cases"] if c["name"] == "dat.bcg_RR_REML_knha")["request"][
        "data"
    ]
    for i, label in enumerate(d["label"]):
        await seed.study(
            label,
            [
                (0, {"events": raw["ai"][i], "total": raw["n1i"][i]}),
                (1, {"events": raw["ci"][i], "total": raw["n2i"][i]}),
            ],
            outcome_id=outcome,
            characteristics={
                # A decimal comma, as typed in Portuguese, still reads as a number.
                "latitude": str(d["mods"]["ablat"][i]).replace(".", ","),
                "alocacao": d["mods"]["alloc"][i],
            },
        )
    return ana, p, outcome


async def test_meta_regression_matches_metafor(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession
) -> None:
    ana, p, outcome = await _bcg(client, make_user, session)
    base = {"outcome_id": outcome, "timepoint": "5 anos", "measure": "RR"}
    for case, mods in ((MR["cases"][0], ["latitude"]), (MR["cases"][3], ["latitude", "alocacao"])):
        req = case["request"]
        r = await client.post(
            f"{p['base']}/analyses/meta-regression",
            headers=ana.headers,
            json={**base, "method": req["method"], "test": req["test"], "moderators": mods},
        )
        assert r.status_code == 200, r.text
        out, e = r.json(), case["expected"]
        assert out["kinds"]["latitude"] == "numeric"
        coef = out["result"]["coefficients"]
        assert out["result"]["k"] == e["k"] == 13
        for i, row in enumerate(coef):
            assert math.isclose(row["estimate"], e["estimate"][i], abs_tol=TOL), (case["name"], i)
            assert math.isclose(row["se"], e["se"][i], abs_tol=TOL)
        assert math.isclose(out["result"]["moderators"]["statistic"], e["qm"], abs_tol=TOL)
    # Two moderators plus a category with 3 levels: 3 coefficients for 13 studies.
    assert out["kinds"]["alocacao"] == "categorical"
    assert "fewer_than_ten_studies_per_moderator" in out["warnings"]


async def test_missing_moderator_and_too_few(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession
) -> None:
    ana, p, outcome = await _bcg(client, make_user, session)
    r = await client.post(
        f"{p['base']}/analyses/meta-regression",
        headers=ana.headers,
        json={
            "outcome_id": outcome,
            "timepoint": "5 anos",
            "measure": "RR",
            "moderators": ["nada"],
        },
    )
    assert r.status_code == 409 and r.json()["code"] == "analysis.meta_regression_too_few"
