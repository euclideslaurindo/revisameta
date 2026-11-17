"""Which studies enter an analysis and why the others do not (stage 3 step 4).

These tests call the real R service (STATS_R_URL), like the reference tests: every
number comes from R. Expected values come from the metafor fixtures in
stats-r/fixtures (public datasets), never typed by hand. Consensus data are written
directly in the database; the extraction flow itself is tested elsewhere.
"""

import math
import uuid
from decimal import Decimal
from typing import Any

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.extraction.models import (
    Extraction,
    ExtractionForm,
    OutcomeData,
    OutcomeMeasure,
    StudyArm,
)
from app.modules.studies.models import Study
from tests.test_consensus import MakeUser, _project
from tests.test_stats_reference import _fixture

META = _fixture()
TOL = META["tolerance"]


def _case(name: str) -> dict[str, Any]:
    return next(c for c in META["cases"] if c["name"] == name)


class Seeder:
    def __init__(self, session: AsyncSession, p: dict[str, Any], form_id: uuid.UUID) -> None:
        self.session, self.p, self.form_id = session, p, form_id

    async def study(
        self,
        label: str,
        arms: list[tuple[int, dict[str, Any]]],  # (group index or -1 for unmapped, outcome data)
        *,
        status: str = "submitted",
        cutoff: Any = 5,
        scale: str | None = "Escala X",
        higher_is_better: bool = True,
        outcome_id: str | None = None,
        timepoint: str = "5 anos",
    ) -> uuid.UUID:
        pid = uuid.UUID(self.p["pid"])
        study = Study(project_id=pid, label=label, design="cohort_retrospective")
        self.session.add(study)
        await self.session.flush()
        extraction = Extraction(
            project_id=pid,
            study_id=study.id,
            form_id=self.form_id,
            kind="consensus",
            status=status,
            characteristics={"cutoff_used": cutoff},
        )
        self.session.add(extraction)
        await self.session.flush()
        outcome = uuid.UUID(outcome_id or self.p["outcome"])
        self.session.add(
            OutcomeMeasure(
                project_id=pid,
                extraction_id=extraction.id,
                outcome_id=outcome,
                scale_name=scale,
                higher_is_better=higher_is_better,
            )
        )
        for position, (group, values) in enumerate(arms):
            arm = StudyArm(
                project_id=pid,
                extraction_id=extraction.id,
                label=f"{label} braço {position}",
                position=position,
                mapped_group_id=uuid.UUID(self.p["groups"][group]) if group >= 0 else None,
            )
            self.session.add(arm)
            await self.session.flush()
            if values:
                self.session.add(
                    OutcomeData(
                        project_id=pid,
                        extraction_id=extraction.id,
                        arm_id=arm.id,
                        outcome_id=outcome,
                        timepoint=timepoint,
                        **{
                            k: (Decimal(str(v)) if isinstance(v, float) else v)
                            for k, v in values.items()
                        },
                    )
                )
        await self.session.commit()
        return study.id


async def _setup(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession, **plan: Any
) -> tuple[Any, dict[str, Any], Seeder]:
    ana = await make_user("Ana")
    p = await _project(client, ana)
    # The helper project starts with one study without consensus.
    await client.get(f"{p['base']}/extraction-form", headers=ana.headers)
    form = (
        await session.scalars(
            select(ExtractionForm).where(ExtractionForm.project_id == uuid.UUID(p["pid"]))
        )
    ).first()
    assert form is not None
    current = (await client.get(f"{p['base']}/analysis-plan", headers=ana.headers)).json()
    body = {
        "version": current["version"],
        "comparison": {"group1_id": p["groups"][0], "group2_id": p["groups"][1]},
        **plan,
    }
    r = await client.put(f"{p['base']}/analysis-plan", json=body, headers=ana.headers)
    assert r.status_code == 200, r.text
    return ana, p, Seeder(session, p, form.id)


async def _preview(
    client: AsyncClient, user: Any, p: dict[str, Any], **body: Any
) -> dict[str, Any]:
    r = await client.post(
        f"{p['base']}/analyses/preview",
        json={"outcome_id": p["outcome"], "timepoint": "5 anos", **body},
        headers=user.headers,
    )
    assert r.status_code == 200, r.text
    return dict(r.json())


async def test_normand_studies_match_metafor(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession
) -> None:
    ana, p, seed = await _setup(client, make_user, session)
    case = _case("dat.normand1999_MD_REML_knha")
    d = case["request"]["data"]
    for i, label in enumerate(d["label"]):
        await seed.study(
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
    out = await _preview(client, ana, p)
    assert out["measure"] == "MD" and out["measure_reason"] == "auto_same_scale"
    assert out["k"] == len(d["label"]) and out["blocks"] == []
    included = {s["label"]: s for s in out["studies"] if s["included"]}
    for label, yi, vi in zip(
        d["label"], case["expected"]["yi"], case["expected"]["vi"], strict=True
    ):
        assert math.isclose(included[label]["yi"], yi, abs_tol=TOL)
        assert math.isclose(included[label]["vi"], vi, abs_tol=TOL)
    # The study of the helper project has no consensus: listed, never hidden.
    assert next(s for s in out["studies"] if not s["included"])["reasons"] == ["no_consensus"]
    assert out["request"]["method"] == "REML" and out["request"]["test"] == "knha"
    assert len(out["request"]["data"]["yi"]) == len(d["label"])


async def test_bcg_risk_ratio_matches_metafor(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession
) -> None:
    ana = await make_user("Ana")
    p = await _project(client, ana)
    r = await client.post(
        f"{p['base']}/outcomes",
        json={"name": "TB", "type": "dichotomous", "timepoints": ["5 anos"]},
        headers=ana.headers,
    )
    outcome = r.json()["id"]
    await client.get(f"{p['base']}/extraction-form", headers=ana.headers)
    form = (
        await session.scalars(
            select(ExtractionForm).where(ExtractionForm.project_id == uuid.UUID(p["pid"]))
        )
    ).first()
    assert form is not None
    current = (await client.get(f"{p['base']}/analysis-plan", headers=ana.headers)).json()
    await client.put(
        f"{p['base']}/analysis-plan",
        headers=ana.headers,
        json={
            "version": current["version"],
            "comparison": {"group1_id": p["groups"][0], "group2_id": p["groups"][1]},
        },
    )
    seed = Seeder(session, p, form.id)
    case = _case("dat.bcg_RR_REML_knha")
    d = case["request"]["data"]
    for i, label in enumerate(d["label"]):
        await seed.study(
            label,
            [
                (0, {"events": d["ai"][i], "total": d["n1i"][i]}),
                (1, {"events": d["ci"][i], "total": d["n2i"][i]}),
            ],
            outcome_id=outcome,
        )
    await seed.study(
        "FICTÍCIO zero eventos",
        [(0, {"events": 0, "total": 30}), (1, {"events": 0, "total": 31})],
        outcome_id=outcome,
    )
    r = await client.post(
        f"{p['base']}/analyses/preview",
        json={"outcome_id": outcome, "timepoint": "5 anos"},
        headers=ana.headers,
    )
    out = r.json()
    assert out["measure"] == "RR" and out["k"] == len(d["label"])
    by_label = {s["label"]: s for s in out["studies"]}
    for label, yi in zip(d["label"], case["expected"]["yi"], strict=True):
        assert math.isclose(by_label[label]["yi"], yi, abs_tol=TOL)
    zero = by_label["FICTÍCIO zero eventos"]
    assert zero["included"] is False and zero["reasons"] == ["no_effect_double_zero"]

    # FICTITIOUS adjusted RR with its CI: only in the adjusted set, converted by R.
    effect = {"measure": "RR", "estimate": "0.62", "ci_low": "0.41", "ci_high": "0.94"}
    await seed.study(
        "FICTÍCIO RR ajustado",
        [
            (
                0,
                {
                    "events": 9,
                    "total": 40,
                    "effect_reported": effect,
                    "adjusted": True,
                    "adjusted_for": "idade",
                },
            ),
            (1, {"events": 14, "total": 41}),
        ],
        outcome_id=outcome,
    )
    r = await client.post(
        f"{p['base']}/analyses/preview",
        headers=ana.headers,
        json={"outcome_id": outcome, "timepoint": "5 anos", "data_set": "adjusted"},
    )
    adjusted = r.json()
    assert adjusted["k"] == 1 and adjusted["blocks"] == ["fewer_than_two_studies"]
    row = next(s for s in adjusted["studies"] if s["label"] == "FICTÍCIO RR ajustado")
    assert row["source"] == "reported_effect" and {"adjusted", "converted"} <= set(row["flags"])
    assert row["conversions"][0]["kind"] == "effect_ci_to_log"
    assert row["conversions"][0]["input"]["estimate"] == 0.62
    # In the unadjusted set the same study enters with its raw counts.
    r = await client.post(
        f"{p['base']}/analyses/preview",
        headers=ana.headers,
        json={"outcome_id": outcome, "timepoint": "5 anos"},
    )
    raw = next(s for s in r.json()["studies"] if s["label"] == "FICTÍCIO RR ajustado")
    assert raw["source"] == "raw" and raw["included"]


async def test_reasons_flags_and_blocks(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession
) -> None:
    ana, p, seed = await _setup(client, make_user, session, cutoff={"value": 5, "rule": "strict"})
    good = {"n": 30, "mean": 92.0, "sd": 12.0, "dispersion_type": "sd"}
    other = {"n": 32, "mean": 85.0, "sd": 11.0, "dispersion_type": "sd"}
    # FICTITIOUS studies, one per situation.
    await seed.study("A ok", [(0, good), (1, other)])
    await seed.study(
        "B EP", [(0, {"n": 30, "mean": 92.0, "se": 2.1, "dispersion_type": "se"}), (1, other)]
    )
    await seed.study("C corte em texto", [(0, good), (1, other)], cutoff="< 5 anos")
    await seed.study("D corte 6", [(0, good), (1, other)], cutoff=6)
    await seed.study("E sem grupo 2", [(0, good), (-1, other)])
    await seed.study("F rascunho", [(0, good), (1, other)], status="draft")
    await seed.study(
        "G mediana",
        [
            (0, {"n": 40, "median": 88.0, "q1": 80.0, "q3": 95.0, "dispersion_type": "iqr"}),
            (1, other),
        ],
    )
    await seed.study(
        "H sem DP", [(0, {"n": 30, "mean": 90.0, "dispersion_type": "not_reported"}), (1, other)]
    )
    await seed.study(
        "I maior é pior", [(0, good), (1, other)], higher_is_better=False, scale="Escala X"
    )
    await seed.study(
        "J mudança", [(0, {**good, "value_type": "change"}), (1, {**other, "value_type": "change"})]
    )
    await seed.study("K tipos misturados", [(0, {**good, "value_type": "change"}), (1, other)])

    out = await _preview(client, ana, p)
    s = {row["label"]: row for row in out["studies"]}
    assert s["A ok"]["included"] and s["A ok"]["flags"] == []
    assert s["B EP"]["included"] and "converted" in s["B EP"]["flags"]
    assert s["B EP"]["conversions"][0]["kind"] == "se_to_sd"
    assert s["C corte em texto"]["reasons"] == ["cutoff_not_numeric"]
    assert s["D corte 6"]["reasons"] == ["cutoff_incompatible"]
    assert s["E sem grupo 2"]["reasons"] == ["missing_group"]
    assert s["F rascunho"]["reasons"] == ["no_consensus"]
    assert s["G mediana"]["included"] and "estimated" in s["G mediana"]["flags"]
    assert s["H sem DP"]["reasons"] == ["missing_dispersion"]
    assert s["I maior é pior"]["inverted"] is True
    assert math.isclose(s["I maior é pior"]["yi"], -s["A ok"]["yi"], abs_tol=TOL)
    assert s["J mudança"]["value_type"] == "change"
    assert s["K tipos misturados"]["reasons"] == ["mixed_value_type_in_study"]
    assert "estimated_data" in out["warnings"] and "direction_inverted" in out["warnings"]
    # MD may mix final values and changes (with a warning); SMD may not.
    assert "mixed_final_change" in out["warnings"] and out["blocks"] == []
    smd = await _preview(client, ana, p, measure="SMD")
    assert smd["blocks"] == ["smd_mixed_final_change"] and smd["request"] is None


async def test_too_few_studies_and_adjusted_effects_apart(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession
) -> None:
    ana, p, seed = await _setup(client, make_user, session)
    good = {"n": 30, "mean": 92.0, "sd": 12.0, "dispersion_type": "sd"}
    other = {"n": 32, "mean": 85.0, "sd": 11.0, "dispersion_type": "sd"}
    await seed.study("A", [(0, good), (1, other)])
    out = await _preview(client, ana, p)
    assert out["k"] == 1 and out["blocks"] == ["fewer_than_two_studies"]
    # A measure that differs from the plan is "not planned".
    plan = (await client.get(f"{p['base']}/analysis-plan", headers=ana.headers)).json()
    await client.put(
        f"{p['base']}/analysis-plan",
        headers=ana.headers,
        json={
            **{k: plan[k] for k in ("comparison", "adjusted", "model")},
            "version": plan["version"],
            "outcomes": [{"outcome_id": p["outcome"], "measure": "MD"}],
        },
    )
    assert (await _preview(client, ana, p, measure="SMD"))["not_planned"] == ["measure"]
    assert (await _preview(client, ana, p))["measure_reason"] == "plan"
    # Studies with only an adjusted effect never enter the unadjusted set.
    adjusted = await _preview(client, ana, p, data_set="adjusted")
    assert adjusted["k"] == 0
    assert next(r for r in adjusted["studies"] if r["label"] == "A")["reasons"] == [
        "no_adjusted_effect"
    ]


async def test_run_through_the_api_matches_metafor(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession
) -> None:
    """11.1, item 3: the same data through the API give the fixture's result."""
    ana, p, seed = await _setup(client, make_user, session)
    d = _case("dat.normand1999_MD_REML_knha")["request"]["data"]
    for i, label in enumerate(d["label"]):
        await seed.study(
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
    url = f"{p['base']}/analyses/run"
    body = {"outcome_id": p["outcome"], "timepoint": "5 anos"}
    for method, test in (("REML", "knha"), ("DL", "z"), ("FE", "z")):
        r = await client.post(
            url, json={**body, "method": method, "test": test}, headers=ana.headers
        )
        assert r.status_code == 200, r.text
        out = r.json()
        expected = _case(f"dat.normand1999_MD_{method}_{test}")["expected"]
        pooled, het = out["result"]["pooled"], out["result"]["heterogeneity"]
        for key in ("estimate", "ci_lb", "ci_ub", "pi_lb", "pi_ub", "p_value"):
            assert math.isclose(pooled[key], expected[key], abs_tol=TOL), (method, key)
        assert math.isclose(het["i2"], expected["i2"], abs_tol=TOL)
        assert out["not_planned"] == ([] if method == "REML" else ["model"])
    assert out["r_meta"]["packages"]["metafor"] == META["metafor_version"]
    assert out["group1_label"] and out["favours_right"] == "group1"

    r = await client.post(
        f"{p['base']}/analyses/forest-plot",
        json={**body, "format": "svg", "lang": "en"},
        headers=ana.headers,
    )
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("image/svg+xml")
    assert b"<svg" in r.content[:500]
    assert "forest-plot_escore" in r.headers["content-disposition"]


async def test_run_is_refused_while_the_assembly_has_a_block(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession
) -> None:
    ana, p, seed = await _setup(client, make_user, session)
    await seed.study(
        "A",
        [
            (0, {"n": 30, "mean": 92.0, "sd": 12.0, "dispersion_type": "sd"}),
            (1, {"n": 32, "mean": 85.0, "sd": 11.0, "dispersion_type": "sd"}),
        ],
    )
    r = await client.post(
        f"{p['base']}/analyses/run",
        headers=ana.headers,
        json={"outcome_id": p["outcome"], "timepoint": "5 anos"},
    )
    assert r.status_code == 409 and r.json()["code"] == "analysis.blocked"


async def test_plausibility_checks_flag_se_typed_as_sd(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession
) -> None:
    """Synthetic case (11.2): FICTITIOUS studies, one with the SE typed as the SD."""
    ana, p, seed = await _setup(client, make_user, session)
    control = {"n": 40, "mean": 85.0, "sd": 15.0, "dispersion_type": "sd"}
    for label, sd in (("A", 15.0), ("B", 14.0), ("C", 16.0), ("D", round(15 / 40**0.5, 4))):
        await seed.study(
            label, [(0, {"n": 40, "mean": 92.0, "sd": sd, "dispersion_type": "sd"}), (1, control)]
        )
    out = await _preview(client, ana, p)
    flagged = {s["label"]: s for s in out["studies"] if s["checks"]}
    assert set(flagged) == {"D"}
    check = flagged["D"]["checks"][0]
    assert check["code"] == "possible_se_as_sd" and check["values"]["typical_sd"] == 15.0
    assert "possible_se_as_sd" in flagged["D"]["flags"] and flagged["D"]["included"]
    assert "plausibility_alerts" in out["warnings"]

    # The thresholds come from the analysis plan.
    plan = (await client.get(f"{p['base']}/analysis-plan", headers=ana.headers)).json()
    assert plan["checks"]["sd_ratio"] == 0.5
    await client.put(
        f"{p['base']}/analysis-plan",
        headers=ana.headers,
        json={
            **{k: plan[k] for k in ("comparison", "adjusted", "model")},
            "version": plan["version"],
            "checks": {**plan["checks"], "sd_ratio": 0.05},
        },
    )
    assert not any(s["checks"] for s in (await _preview(client, ana, p))["studies"])

    # Block E after the model: influence (metafor's criteria) flags study D.
    r = await client.post(
        f"{p['base']}/analyses/run",
        headers=ana.headers,
        json={"outcome_id": p["outcome"], "timepoint": "5 anos", "measure": "SMD"},
    )
    assert r.status_code == 200, r.text
    run = r.json()
    d = next(s for s in run["assembly"]["studies"] if s["label"] == "D")
    assert "influential" in d["flags"] and "influential_studies" in run["warnings"]


async def test_reported_p_that_does_not_match_the_data_is_flagged(
    client: AsyncClient, make_user: MakeUser, session: AsyncSession
) -> None:
    ana, p, seed = await _setup(client, make_user, session)
    other = {"n": 30, "mean": 85.0, "sd": 12.0, "dispersion_type": "sd"}
    # FICTITIOUS: a 7-point difference with SD 12 and n 30 is clearly not p = 0.9.
    await seed.study(
        "P errado",
        [
            (0, {"n": 30, "mean": 92.0, "sd": 12.0, "dispersion_type": "sd", "p_value": 0.9}),
            (1, other),
        ],
    )
    await seed.study(
        "Outro", [(0, {"n": 30, "mean": 90.0, "sd": 12.0, "dispersion_type": "sd"}), (1, other)]
    )
    out = await _preview(client, ana, p)
    row = next(s for s in out["studies"] if s["label"] == "P errado")
    assert row["checks"][0]["code"] == "p_inconsistent"
    assert row["checks"][0]["values"]["p_reported"] == 0.9
