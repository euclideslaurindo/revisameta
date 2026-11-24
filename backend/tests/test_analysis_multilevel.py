"""Multilevel model through the API (stage 8 step 2), with the real R service.

The R function is checked against metafor::rma.mv in stats-r (fixtures/multilevel.json,
public dat.konstantopoulos2011). Here: the same assembly runs for each time point, every
study is one cluster, and the API returns exactly what R computes for those effects.
Data: public dat.bcg, copied to a second (FICTITIOUS) time point.
"""

import math
import uuid

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.stats_client import get_stats_client
from app.modules.extraction.models import OutcomeData
from app.modules.protocol.models import Outcome
from tests.test_analysis_subgroups import _bcg
from tests.test_consensus import MakeUser


async def test_two_time_points_with_the_study_as_cluster(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession
) -> None:
    ana, p, outcome = await _bcg(client, make_user, session)
    row = await session.get(Outcome, uuid.UUID(outcome))
    assert row is not None
    row.timepoints = ["5 anos", "10 anos"]
    for data in list(await session.scalars(select(OutcomeData))):
        if data.outcome_id == row.id and data.timepoint == "5 anos":
            clone = {
                c.name: getattr(data, c.name)
                for c in OutcomeData.__table__.columns
                if c.name not in ("id", "created_at", "updated_at", "version")
            }
            session.add(OutcomeData(**{**clone, "timepoint": "10 anos"}))
    await session.commit()

    body = {"outcome_id": outcome, "timepoints": ["5 anos", "10 anos"], "measure": "RR"}
    r = await client.post(f"{p['base']}/analyses/multilevel", headers=ana.headers, json=body)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["k"] == 26 and out["studies"] == 13
    effects = out["result"]["effects"]
    assert {e["study"] for e in effects} == {e["study"] for e in effects[:13]}

    direct = await get_stats_client().multilevel(
        {
            "measure": "RR",
            "method": "REML",
            "test": "z",
            "data": {
                "label": [e["label"] for e in effects],
                "study": [e["study"] for e in effects],
                "yi": [e["yi"] for e in effects],
                "vi": [e["vi"] for e in effects],
            },
        }
    )
    for key in ("estimate", "ci_lb", "ci_ub"):
        assert math.isclose(out["result"]["pooled"][key], direct.result["pooled"][key])

    one = {**body, "timepoints": ["5 anos", "20 anos"]}
    r = await client.post(f"{p['base']}/analyses/multilevel", headers=ana.headers, json=one)
    assert r.status_code == 422  # unknown time point
