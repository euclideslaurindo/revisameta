"""Sensitivity analyses (docs/modulos.md 7.7 "Análises adicionais"; stage 4 step 1).

Each scenario reruns the main analysis changing one thing, so the user sees whether
the conclusion holds. Every number is computed by the R service.

- leave_one_out: the model without each study in turn (metafor::leave1out).
- exclude_high_risk_of_bias: without the studies at the worst level of their
  instrument (stage 4 decision): RoB 2 "high"; ROBINS-I "serious" and "critical";
  ROBINS-E "high" and "very high"; JBI, NOS and generic the worst level of the group's
  rule. Studies without a final risk-of-bias assessment are left out, with a warning.
- exclude_estimated_data: without studies whose numbers were estimated (mean from the
  median) or derived (from t or p).
- fixed_vs_random: fixed effect if the main model is random, and REML otherwise.
- other_estimator: the other heterogeneity estimators (REML, DL, Paule-Mandel).
"""

import uuid
from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.integrations.stats_client import StatsClient
from app.modules.analysis.run import RunIn, RunOut, run
from app.modules.projects.access import ProjectContext
from app.modules.protocol.analysis_plan import current_plan
from app.modules.risk_of_bias.catalog import Template
from app.modules.risk_of_bias.models import RobAssessment, RobJudgement, RobStudyTool, RobTool
from app.modules.risk_of_bias.rules import group_levels

Scenario = Literal[
    "leave_one_out",
    "exclude_high_risk_of_bias",
    "exclude_estimated_data",
    "fixed_vs_random",
    "other_estimator",
]

# Worst levels per instrument (stage 4 decision, docs/estatistica.md).
WORST: dict[str, set[str]] = {
    "rob2": {"high"},
    "robins_i_2016": {"serious", "critical"},
    "robins_i_v2": {"serious", "critical"},
    "robins_e": {"high", "very_high"},
}
# For the group's rule (JBI, NOS, generic): the level with the highest rank.
RANK = {
    "low": 0,
    "good": 0,
    "low_except_confounding": 1,
    "moderate": 1,
    "some_concerns": 1,
    "fair": 1,
    "high": 2,
    "serious": 2,
    "poor": 2,
    "critical": 3,
    "very_high": 3,
}


class SensitivityIn(RunIn):
    scenario: Scenario


class ScenarioResult(BaseModel):
    label: str  # code of the variant, e.g. "without_high_risk", "FE", "DL"
    method: str
    test: str
    k: int
    left_out: list[str]
    estimate: float | None = None
    ci_lb: float | None = None
    ci_ub: float | None = None
    pi_lb: float | None = None
    pi_ub: float | None = None
    p_value: float | None = None
    i2: float | None = None
    tau2: float | None = None
    problem: str | None = None  # not_enough_studies


class SensitivityOut(BaseModel):
    scenario: Scenario
    planned: bool
    measure: str
    main: ScenarioResult
    scenarios: list[ScenarioResult]
    leave_one_out: list[dict[str, Any]]
    warnings: list[str]
    no_assessment: list[str]  # studies left out of the RoB scenario for lack of a final judgement


def _summary(
    label: str, method: str, test: str, result: dict[str, Any], left_out: list[str]
) -> ScenarioResult:
    pooled = result.get("pooled", {})
    het = result.get("heterogeneity", {})
    return ScenarioResult(
        label=label,
        method=method,
        test=test,
        k=result.get("k", 0),
        left_out=left_out,
        estimate=pooled.get("estimate"),
        ci_lb=pooled.get("ci_lb"),
        ci_ub=pooled.get("ci_ub"),
        pi_lb=pooled.get("pi_lb"),
        pi_ub=pooled.get("pi_ub"),
        p_value=pooled.get("p_value"),
        i2=het.get("i2"),
        tau2=het.get("tau2"),
    )


async def _rerun(
    stats: StatsClient, main: RunOut, label: str, method: str, test: str, keep: list[str]
) -> ScenarioResult:
    request = main.assembly.request or {}
    data = request.get("data", {})
    labels: list[str] = data.get("label", [])
    left_out = [lab for lab in labels if lab not in keep]
    index = [i for i, lab in enumerate(labels) if lab in keep]
    if method == "FE":
        test = "z"
    if len(index) < 2:
        return ScenarioResult(
            label=label,
            method=method,
            test=test,
            k=len(index),
            left_out=left_out,
            problem="not_enough_studies",
        )
    subset = {key: [values[i] for i in index] for key, values in data.items()}
    response = await stats.meta_analysis(
        {**request, "method": method, "test": test, "data": subset}
    )
    if not response.ok:
        raise AppError("error.stats_failed", status_code=502)
    return _summary(label, method, test, response.result, left_out)


async def _risk_levels(
    session: AsyncSession, ctx: ProjectContext, main: RunOut
) -> dict[str, tuple[str | None, set[str]]]:
    """Final overall judgement of each included study for this result, and the worst levels."""
    assembly = main.assembly
    ids = [s.study_id for s in assembly.studies if s.included]
    choices = {
        c.study_id: c.tool_id
        for c in await session.scalars(select(RobStudyTool).where(RobStudyTool.study_id.in_(ids)))
    }
    tools = {
        t.id: t
        for t in await session.scalars(select(RobTool).where(RobTool.project_id == ctx.project.id))
    }
    assessments = list(
        await session.scalars(
            select(RobAssessment).where(
                RobAssessment.study_id.in_(ids),
                RobAssessment.kind.in_(("consensus", "imported")),
                RobAssessment.status != "draft",
            )
        )
    )
    overall = {
        j.assessment_id: j.final
        for j in await session.scalars(
            select(RobJudgement).where(
                RobJudgement.assessment_id.in_([a.id for a in assessments]),
                RobJudgement.domain_key.is_(None),
            )
        )
    }
    out: dict[str, tuple[str | None, set[str]]] = {}
    for study in assembly.studies:
        if not study.included:
            continue
        tool = tools.get(choices.get(study.study_id, uuid.UUID(int=0)))
        if tool is None:
            out[study.label] = (None, set())
            continue
        template = Template.model_validate(tool.structure)
        target = (
            (assembly.outcome_id, assembly.timepoint)
            if template.scope == "result"
            else (None, None)
        )
        final = next(
            (
                overall.get(a.id)
                for a in assessments
                if a.study_id == study.study_id
                and a.tool_id == tool.id
                and (a.outcome_id, a.timepoint) == target
            ),
            None,
        )
        if tool.template_key in WORST:
            worst = WORST[tool.template_key]
        else:
            levels = group_levels(tool.overall_rule)
            top = max(RANK.get(level, 0) for level in levels)
            worst = {level for level in levels if RANK.get(level, 0) == top}
        out[study.label] = (final, worst)
    return out


async def sensitivity(
    session: AsyncSession, ctx: ProjectContext, stats: StatsClient, data: SensitivityIn
) -> SensitivityOut:
    main = await run(session, ctx, stats, data)
    plan = current_plan(ctx)
    planned_names = set(plan.sensitivity)
    planned = data.scenario in planned_names
    labels: list[str] = (main.assembly.request or {}).get("data", {}).get("label", [])
    base = _summary("main", main.method, main.test, main.result, [])
    scenarios: list[ScenarioResult] = []
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    no_assessment: list[str] = []

    if data.scenario == "leave_one_out":
        request = main.assembly.request or {}
        response = await stats.leave_one_out({**request, "method": main.method, "test": main.test})
        if not response.ok:
            warnings.append("leave_one_out_needs_three_studies")
        else:
            rows = response.result["rows"]
    elif data.scenario == "exclude_high_risk_of_bias":
        levels = await _risk_levels(session, ctx, main)
        no_assessment = [lab for lab, (final, _) in levels.items() if final is None]
        keep = [
            lab
            for lab, (final, worst) in levels.items()
            if final is not None and final not in worst
        ]
        if no_assessment:
            warnings.append("studies_without_risk_of_bias")
        scenarios.append(
            await _rerun(stats, main, "without_high_risk", main.method, main.test, keep)
        )
    elif data.scenario == "exclude_estimated_data":
        estimated = {
            s.label
            for s in main.assembly.studies
            if s.included and {"estimated", "derived"} & set(s.flags)
        }
        keep = [lab for lab in labels if lab not in estimated]
        scenarios.append(
            await _rerun(stats, main, "without_estimated", main.method, main.test, keep)
        )
    elif data.scenario == "fixed_vs_random":
        other = "REML" if main.method == "FE" else "FE"
        scenarios.append(await _rerun(stats, main, other, other, "knha", labels))
    else:
        for method in ("REML", "DL", "PM"):
            if method != main.method:
                scenarios.append(await _rerun(stats, main, method, method, main.test, labels))
    return SensitivityOut(
        scenario=data.scenario,
        planned=planned,
        measure=main.assembly.measure,
        main=base,
        scenarios=scenarios,
        leave_one_out=rows,
        warnings=warnings,
        no_assessment=no_assessment,
    )
