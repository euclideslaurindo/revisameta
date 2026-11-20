"""Egger's test and funnel plot through the API (stage 4 step 3), with the real R service.

Expected values come from stats-r/fixtures/egger.json (metafor::regtest, public dat.bcg).
"""

import math

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.test_analysis_assembly import TOL
from tests.test_analysis_subgroups import _bcg
from tests.test_consensus import MakeUser
from tests.test_stats_reference import _fixture

EGGER = _fixture("egger.json")


async def test_egger_matches_metafor_and_warns_below_ten_studies(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession
) -> None:
    ana, p, outcome = await _bcg(client, make_user, session)
    body = {"outcome_id": outcome, "timepoint": "5 anos", "measure": "RR"}
    for case in [c for c in EGGER["cases"] if c["name"].startswith("dat.bcg")]:
        req = case["request"]
        r = await client.post(
            f"{p['base']}/analyses/egger",
            headers=ana.headers,
            json={**body, "method": req["method"], "test": req["test"]},
        )
        assert r.status_code == 200, r.text
        out, e = r.json(), case["expected"]
        assert out["k"] == e["k"] == 13 and out["few_studies"] is False
        for key in ("statistic", "p_value", "limit_estimate"):
            assert math.isclose(out["result"][key], e[key], abs_tol=TOL), (case["name"], key)


async def test_funnel_plot_is_a_file(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession
) -> None:
    ana, p, outcome = await _bcg(client, make_user, session)
    r = await client.post(
        f"{p['base']}/analyses/funnel-plot",
        headers=ana.headers,
        json={"outcome_id": outcome, "timepoint": "5 anos", "measure": "RR", "format": "svg"},
    )
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("image/svg+xml")
    assert "funnel-plot" in r.headers["content-disposition"]
    assert b"<svg" in r.content
