"""Sensitivity analyses through the API (stage 4 step 1), with the real R service.

Expected values come from the metafor fixtures (public datasets), never typed by hand.
"""

import math
import uuid
from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.risk_of_bias.models import RobAssessment, RobJudgement, RobStudyTool
from tests.test_analysis_assembly import TOL, Seeder, _case, _setup
from tests.test_consensus import MakeUser
from tests.test_stats_reference import _fixture

L1O = _fixture("leave-one-out.json")


async def _normand(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession
) -> tuple[Any, dict[str, Any], Seeder, dict[str, uuid.UUID]]:
    ana, p, seed = await _setup(client, make_user, session)
    d = _case("dat.normand1999_MD_REML_knha")["request"]["data"]
    ids = {}
    for i, label in enumerate(d["label"]):
        ids[label] = await seed.study(
            label,
            [
                (
                    0,
                    {
                        "n": d["n1i"][i],
                        "mean": float(d["m1i"][i]),
                        "sd": float(d["sd1i"][i]),
                        "dispersion_type": "sd",
                    },
                ),
                (
                    1,
                    {
                        "n": d["n2i"][i],
                        "mean": float(d["m2i"][i]),
                        "sd": float(d["sd2i"][i]),
                        "dispersion_type": "sd",
                    },
                ),
            ],
        )
    return ana, p, seed, ids


async def _sens(
    client: AsyncClient, user: Any, p: dict[str, Any], scenario: str, **extra: Any
) -> dict[str, Any]:
    r = await client.post(
        f"{p['base']}/analyses/sensitivity",
        headers=user.headers,
        json={"outcome_id": p["outcome"], "timepoint": "5 anos", "scenario": scenario, **extra},
    )
    assert r.status_code == 200, r.text
    return dict(r.json())


async def test_leave_one_out_and_model_scenarios_match_metafor(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession
) -> None:
    ana, p, _, _ = await _normand(client, make_user, session)
    out = await _sens(client, ana, p, "leave_one_out")
    case = next(c for c in L1O["cases"] if c["name"] == "dat.normand1999_MD_REML_knha")
    expected = {
        label: (est, lb)
        for label, est, lb in zip(
            case["request"]["data"]["label"],
            case["expected"]["estimate"],
            case["expected"]["ci_lb"],
            strict=True,
        )
    }
    # The API lists studies by name; the fixture follows the dataset order.
    assert len(out["leave_one_out"]) == len(expected)
    for row in out["leave_one_out"]:
        est, lb = expected[row["omitted"]]
        assert math.isclose(row["estimate"], est, abs_tol=TOL), row["omitted"]
        assert math.isclose(row["ci_lb"], lb, abs_tol=TOL), row["omitted"]
    assert out["planned"] is False  # not in the plan's sensitivity list

    out = await _sens(client, ana, p, "fixed_vs_random")
    fe = _case("dat.normand1999_MD_FE_z")["expected"]
    assert out["scenarios"][0]["label"] == "FE"
    assert math.isclose(out["scenarios"][0]["estimate"], fe["estimate"], abs_tol=TOL)

    out = await _sens(client, ana, p, "other_estimator")
    by_label = {s["label"]: s for s in out["scenarios"]}
    assert set(by_label) == {"DL", "PM"}
    dl = _case("dat.normand1999_MD_DL_knha")["expected"]
    assert math.isclose(by_label["DL"]["estimate"], dl["estimate"], abs_tol=TOL)
    assert math.isclose(by_label["DL"]["ci_ub"], dl["ci_ub"], abs_tol=TOL)


async def test_without_high_risk_of_bias_follows_the_worst_level_rule(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession
) -> None:
    ana, p, _, ids = await _normand(client, make_user, session)
    rob2 = (
        await client.post(
            f"{p['base']}/rob/tools", json={"template_key": "rob2"}, headers=ana.headers
        )
    ).json()
    pid, tool, outcome = uuid.UUID(p["pid"]), uuid.UUID(rob2["id"]), uuid.UUID(p["outcome"])
    # FICTITIOUS judgements: two studies high, one without a final assessment, the rest low.
    judgements = {"Edinburgh": "high", "Uppsala": "high", "Umea": None}
    for label, study_id in ids.items():
        session.add(
            RobStudyTool(
                project_id=pid, study_id=study_id, tool_id=tool, confirmed_by=uuid.UUID(ana.id)
            )
        )
        if label in judgements and judgements[label] is None:
            continue
        a = RobAssessment(
            id=uuid.uuid4(),
            project_id=pid,
            study_id=study_id,
            tool_id=tool,
            outcome_id=outcome,
            timepoint="5 anos",
            kind="consensus",
            status="submitted",
            variants={},
        )
        session.add(a)
        await session.flush()
        session.add(
            RobJudgement(
                project_id=pid,
                assessment_id=a.id,
                domain_key=None,
                final=judgements.get(label, "low"),
            )
        )
    await session.commit()

    out = await _sens(client, ana, p, "exclude_high_risk_of_bias")
    scenario = out["scenarios"][0]
    assert sorted(scenario["left_out"]) == ["Edinburgh", "Umea", "Uppsala"]
    assert scenario["k"] == len(ids) - 3
    assert out["no_assessment"] == ["Umea"] and "studies_without_risk_of_bias" in out["warnings"]


async def test_without_estimated_data(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession
) -> None:
    ana, p, seed = await _setup(client, make_user, session)
    other = {"n": 32, "mean": 85.0, "sd": 11.0, "dispersion_type": "sd"}
    for label in ("A", "B", "C"):
        await seed.study(
            label, [(0, {"n": 30, "mean": 92.0, "sd": 12.0, "dispersion_type": "sd"}), (1, other)]
        )
    await seed.study(
        "Mediana",
        [
            (0, {"n": 40, "median": 88.0, "q1": 80.0, "q3": 95.0, "dispersion_type": "iqr"}),
            (1, other),
        ],
    )
    out = await _sens(client, ana, p, "exclude_estimated_data")
    assert out["scenarios"][0]["left_out"] == ["Mediana"] and out["scenarios"][0]["k"] == 3


async def test_scenarios_with_fewer_than_two_studies_say_so(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession
) -> None:
    ana, p, seed = await _setup(client, make_user, session)
    other = {"n": 32, "mean": 85.0, "sd": 11.0, "dispersion_type": "sd"}
    await seed.study(
        "A", [(0, {"n": 30, "mean": 92.0, "sd": 12.0, "dispersion_type": "sd"}), (1, other)]
    )
    for label in ("M1", "M2"):
        await seed.study(
            label,
            [
                (0, {"n": 40, "median": 88.0, "q1": 80.0, "q3": 95.0, "dispersion_type": "iqr"}),
                (1, other),
            ],
        )
    out = await _sens(client, ana, p, "exclude_estimated_data")
    scenario = out["scenarios"][0]
    assert scenario["k"] == 1 and scenario["problem"] == "not_enough_studies"
    assert scenario["estimate"] is None
