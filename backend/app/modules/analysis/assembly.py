"""Which studies enter an analysis, with which numbers, and why the others do not
(docs/modulos.md 7.7, step 1 of the wizard; stage 3 step 4).

The backend only chooses and organizes data; every number is computed by the R
service: conversions (SE, CI or median to SD), combination of arms, the effect of
each study (escalc, with the sign inverted for "higher is worse" scales) and, later,
the model. Each study ends as yi/vi on the analysis scale, with the trail of what
was done to its numbers.

Data sets never mixed (7.7): raw group data and unadjusted effects reported by the
article form the "unadjusted" set; adjusted effects (OR/RR with CI) the "adjusted"
set. The project plan says which one runs (default: separately).
"""

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.integrations.stats_client import StatsClient
from app.modules.extraction.models import (
    AlertStatus,
    CheckAlert,
    Extraction,
    OutcomeData,
    OutcomeMeasure,
    StudyArm,
)
from app.modules.projects.access import ProjectContext
from app.modules.protocol.analysis_plan import AnalysisPlan, current_plan, cutoff_status
from app.modules.protocol.models import Outcome
from app.modules.studies.models import Study

Measure = Literal["MD", "SMD", "OR", "RR", "RD"]
DataSet = Literal["unadjusted", "adjusted"]
FINAL_STATUSES = ("submitted", "locked")
RATIO = ("OR", "RR")


# ---- Schemas -------------------------------------------------------------------------


class AssemblyIn(BaseModel):
    outcome_id: uuid.UUID
    timepoint: str = Field(min_length=1, max_length=60)
    measure: Measure | None = None  # None: the plan's measure, or the automatic choice
    data_set: DataSet | None = None  # None: from the plan


class GroupValues(BaseModel):
    n: float | None = None
    mean: float | None = None
    sd: float | None = None
    events: float | None = None
    total: float | None = None
    arms: list[str] = Field(default_factory=list)


class StudyRow(BaseModel):
    study_id: uuid.UUID
    label: str
    included: bool
    reasons: list[str]  # why it is out (codes), empty when included
    flags: list[str]  # included but worth a look: estimated, converted, alerts...
    source: str | None  # raw | reported_effect
    value_type: str | None
    scale_name: str | None
    higher_is_better: bool | None
    cutoff: str | None
    cutoff_status: str | None
    group1: GroupValues | None
    group2: GroupValues | None
    conversions: list[dict[str, Any]]
    yi: float | None = None
    vi: float | None = None
    inverted: bool = False


class AssemblyOut(BaseModel):
    outcome_id: uuid.UUID
    outcome_name: str
    outcome_type: str
    timepoint: str
    measure: Measure
    measure_reason: (
        str  # plan | chosen | auto_same_scale | auto_different_scales | auto_dichotomous
    )
    data_set: DataSet
    k: int
    studies: list[StudyRow]
    blocks: list[str]  # the analysis cannot run
    warnings: list[str]
    not_planned: list[str]  # settings different from the analysis plan
    request: dict[str, Any] | None  # what goes to /meta-analysis (yi, vi per study)


# ---- Loading -------------------------------------------------------------------------


@dataclass
class _Study:
    study: Study
    extraction: Extraction | None
    arms: list[StudyArm] = field(default_factory=list)
    rows: list[OutcomeData] = field(default_factory=list)
    measure: OutcomeMeasure | None = None
    open_alerts: int = 0


async def _load(
    session: AsyncSession, ctx: ProjectContext, outcome_id: uuid.UUID, timepoint: str
) -> list[_Study]:
    studies = list(
        await session.scalars(
            select(Study).where(Study.project_id == ctx.project.id).order_by(Study.label)
        )
    )
    consensus = {
        e.study_id: e
        for e in await session.scalars(
            select(Extraction).where(
                Extraction.project_id == ctx.project.id, Extraction.kind == "consensus"
            )
        )
    }
    ids = [e.id for e in consensus.values()]
    arms = list(await session.scalars(select(StudyArm).where(StudyArm.extraction_id.in_(ids))))
    rows = list(
        await session.scalars(
            select(OutcomeData).where(
                OutcomeData.extraction_id.in_(ids),
                OutcomeData.outcome_id == outcome_id,
                OutcomeData.timepoint == timepoint,
            )
        )
    )
    measures = list(
        await session.scalars(
            select(OutcomeMeasure).where(
                OutcomeMeasure.extraction_id.in_(ids), OutcomeMeasure.outcome_id == outcome_id
            )
        )
    )
    alerts = list(
        await session.scalars(
            select(CheckAlert).where(
                CheckAlert.extraction_id.in_(ids), CheckAlert.status == AlertStatus.OPEN
            )
        )
    )
    out = []
    for study in studies:
        e = consensus.get(study.id)
        item = _Study(study=study, extraction=e)
        if e is not None:
            item.arms = sorted(
                (a for a in arms if a.extraction_id == e.id), key=lambda a: a.position
            )
            item.rows = [r for r in rows if r.extraction_id == e.id]
            item.measure = next((m for m in measures if m.extraction_id == e.id), None)
            item.open_alerts = len([a for a in alerts if a.extraction_id == e.id])
        out.append(item)
    return out


def _f(value: Decimal | int | None) -> float | None:
    return None if value is None else float(value)


# ---- Choosing the numbers of each study ----------------------------------------------


@dataclass
class _ArmPlan:
    """The numbers of one arm, and the conversions R must do to get them."""

    label: str
    n: float | None
    mean: float | None = None
    sd: float | None = None
    events: float | None = None
    total: float | None = None
    convert: dict[str, Any] | None = None  # one /convert item, when needed
    problem: str | None = None


def _continuous_arm(arm: StudyArm, row: OutcomeData) -> _ArmPlan:
    n = _f(row.n) if row.n is not None else _f(arm.n)
    plan = _ArmPlan(label=arm.label, n=n, mean=_f(row.mean))
    if n is None or n <= 0:
        plan.problem = "missing_n"
        return plan
    kind = row.dispersion_type
    if kind == "sd" and row.sd is not None and plan.mean is not None:
        plan.sd = _f(row.sd)
    elif kind == "se" and row.se is not None and plan.mean is not None:
        plan.convert = {"kind": "se_to_sd", "se": _f(row.se), "n": n}
    elif (
        kind == "ci95"
        and row.ci_low is not None
        and row.ci_high is not None
        and plan.mean is not None
    ):
        plan.convert = {
            "kind": "ci_to_sd",
            "ci_lb": _f(row.ci_low),
            "ci_ub": _f(row.ci_high),
            "n": n,
        }
    elif kind in ("iqr", "range") and row.median is not None:
        item: dict[str, Any] = {"kind": "median_to_mean_sd", "median": _f(row.median), "n": n}
        for key in ("q1", "q3", "min", "max"):
            value = getattr(row, key)
            if value is not None:
                item[key] = _f(value)
        plan.convert = item
    elif plan.mean is None and row.median is None:
        plan.problem = "missing_mean"
    else:
        plan.problem = "missing_dispersion"
    return plan


def _dichotomous_arm(arm: StudyArm, row: OutcomeData) -> _ArmPlan:
    plan = _ArmPlan(label=arm.label, n=_f(row.total), events=_f(row.events), total=_f(row.total))
    if row.events is None or row.total is None or row.total <= 0:
        plan.problem = "missing_events"
    return plan


def _reported_effect(
    rows: list[OutcomeData], data_set: DataSet, measure: Measure
) -> tuple[dict[str, Any] | None, str | None]:
    """The effect reported by the article for this data set, or why it cannot be used."""
    wanted_adjusted = data_set == "adjusted"
    effects = [r for r in rows if r.effect_reported and bool(r.adjusted) == wanted_adjusted]
    if not effects:
        return None, None
    effect = effects[0].effect_reported or {}
    if effect.get("measure") != measure or measure not in RATIO:
        return None, "reported_measure_differs"
    if effect.get("ci_low") is None or effect.get("ci_high") is None:
        return None, "reported_effect_without_ci"
    return {
        "kind": "effect_ci_to_log",
        "estimate": float(effect["estimate"]),
        "ci_lb": float(effect["ci_low"]),
        "ci_ub": float(effect["ci_high"]),
    }, None


# ---- Assembly ------------------------------------------------------------------------


def _auto_measure(outcome: Outcome, items: list[_Study]) -> tuple[Measure, str]:
    if outcome.type == "dichotomous":
        return "RR", "auto_dichotomous"
    scales = {
        (i.measure.scale_name or "").strip().lower()
        for i in items
        if i.measure is not None and i.rows
    }
    if len(scales) == 1 and "" not in scales:
        return "MD", "auto_same_scale"
    return "SMD", "auto_different_scales"


async def assemble(
    session: AsyncSession, ctx: ProjectContext, stats: StatsClient, data: AssemblyIn
) -> AssemblyOut:
    outcome = (
        await session.scalars(
            select(Outcome).where(
                Outcome.id == data.outcome_id, Outcome.project_id == ctx.project.id
            )
        )
    ).first()
    if outcome is None or data.timepoint not in outcome.timepoints:
        raise AppError("analysis.unknown_result", status_code=422)
    plan: AnalysisPlan = current_plan(ctx)
    planned = next((o for o in plan.outcomes if o.outcome_id == outcome.id), None)
    items = await _load(session, ctx, outcome.id, data.timepoint)

    not_planned: list[str] = []
    if data.measure is not None:
        measure: Measure = data.measure
        measure_reason = "chosen"
        if planned and planned.measure not in ("auto", data.measure):
            not_planned.append("measure")
    elif planned and planned.measure != "auto":
        measure, measure_reason = planned.measure, "plan"
    else:
        measure, measure_reason = _auto_measure(outcome, items)
    allowed = ("MD", "SMD") if outcome.type == "continuous" else ("OR", "RR", "RD")
    if measure not in allowed:
        raise AppError("analysis.measure_mismatch", status_code=422)
    if planned and planned.timepoint and planned.timepoint != data.timepoint:
        not_planned.append("timepoint")
    if planned is None and plan.outcomes:
        not_planned.append("outcome")
    plan_set: DataSet = "adjusted" if plan.adjusted == "adjusted_only" else "unadjusted"
    data_set: DataSet = data.data_set or plan_set
    if plan.adjusted != "separate" and data_set != plan_set:
        not_planned.append("data_set")

    groups = plan.comparison
    rows_out: list[StudyRow] = []
    pending: list[tuple[StudyRow, dict[str, list[_ArmPlan]], dict[str, Any] | None]] = []
    for item in items:
        reasons: list[str] = []
        flags: list[str] = []
        row = StudyRow(
            study_id=item.study.id,
            label=item.study.label,
            included=False,
            reasons=reasons,
            flags=flags,
            source=None,
            value_type=None,
            scale_name=item.measure.scale_name if item.measure else None,
            higher_is_better=item.measure.higher_is_better
            if item.measure
            else outcome.higher_is_better,
            cutoff=None,
            cutoff_status=None,
            group1=None,
            group2=None,
            conversions=[],
        )
        rows_out.append(row)
        # Pydantic copies lists on construction: write to the row's own lists.
        reasons, flags = row.reasons, row.flags
        e = item.extraction
        if e is None or e.status not in FINAL_STATUSES:
            reasons.append("no_consensus")
            continue
        if item.open_alerts:
            flags.append("open_alerts")
        cutoff_value = (e.characteristics or {}).get("cutoff_used")
        row.cutoff = None if cutoff_value is None else str(cutoff_value)
        status = cutoff_status(cutoff_value, plan)
        row.cutoff_status = status
        if status in ("incompatible", "not_numeric", "missing"):
            reasons.append(f"cutoff_{status}")
        elif status == "tolerated":
            flags.append("cutoff_tolerated")
        if not item.rows:
            reasons.append("no_data_for_result")
            continue
        if groups is None:
            reasons.append("no_comparison_in_plan")
            continue
        arms1 = [a for a in item.arms if a.mapped_group_id == groups.group1_id]
        arms2 = [a for a in item.arms if a.mapped_group_id == groups.group2_id]
        if not arms1 or not arms2:
            reasons.append("missing_group")
            continue

        reported, problem = _reported_effect(item.rows, data_set, measure)
        if reported is not None:
            if reasons:
                continue
            row.source = "reported_effect"
            flags.append("reported_effect")
            if data_set == "adjusted":
                flags.append("adjusted")
            pending.append((row, {}, reported))
            continue
        if data_set == "adjusted":
            reasons.append(problem or "no_adjusted_effect")
            continue

        by_arm = {r.arm_id: r for r in item.rows}
        sides: dict[str, list[_ArmPlan]] = {}
        value_types: set[str] = set()
        for side, arms in (("group1", arms1), ("group2", arms2)):
            plans: list[_ArmPlan] = []
            for arm in arms:
                data_row = by_arm.get(arm.id)
                if data_row is None:
                    plans.append(_ArmPlan(label=arm.label, n=None, problem="missing_arm_data"))
                    continue
                value_types.add(data_row.value_type)
                plans.append(
                    _continuous_arm(arm, data_row)
                    if outcome.type == "continuous"
                    else _dichotomous_arm(arm, data_row)
                )
            sides[side] = plans
        problems = sorted({p.problem for plans in sides.values() for p in plans if p.problem})
        reasons.extend(problems)
        if len(value_types) > 1:
            reasons.append("mixed_value_type_in_study")
        if reasons:
            continue
        row.source = "raw"
        row.value_type = value_types.pop() if value_types else None
        pending.append((row, sides, None))

    await _compute(stats, measure, outcome.type, pending)
    included = [r for r in rows_out if r.included]

    blocks: list[str] = []
    warnings: list[str] = []
    if len(included) < 2:
        blocks.append("fewer_than_two_studies")
    value_types = {r.value_type for r in included if r.value_type}
    if measure == "SMD" and len(value_types) > 1:
        blocks.append("smd_mixed_final_change")
    elif len(value_types) > 1:
        warnings.append("mixed_final_change")
    if 2 <= len(included) < 5:
        warnings.append("few_studies")
    if any("estimated" in r.flags for r in included):
        warnings.append("estimated_data")
    if any("open_alerts" in r.flags for r in included):
        warnings.append("studies_with_open_alerts")
    if any(r.inverted for r in included):
        warnings.append("direction_inverted")
    labels = [r.label for r in included]
    if len(labels) != len(set(labels)):
        blocks.append("duplicate_study")

    request = None
    if not blocks:
        request = {
            "measure": measure,
            "method": plan.model.method,
            "test": plan.model.test,
            "data": {
                "label": labels,
                "yi": [r.yi for r in included],
                "vi": [r.vi for r in included],
            },
        }
    return AssemblyOut(
        outcome_id=outcome.id,
        outcome_name=outcome.name,
        outcome_type=outcome.type,
        timepoint=data.timepoint,
        measure=measure,
        measure_reason=measure_reason,
        data_set=data_set,
        k=len(included),
        studies=rows_out,
        blocks=blocks,
        warnings=warnings,
        not_planned=not_planned,
        request=request,
    )


# ---- Asking R for the numbers ----------------------------------------------------------


async def _compute(
    stats: StatsClient,
    measure: Measure,
    outcome_type: str,
    pending: list[tuple[StudyRow, dict[str, Any], dict[str, Any] | None]],
) -> None:
    """Conversions, combination of arms and effect of each study, all done by R."""
    if not pending:
        return
    # 1. Every conversion in one call.
    items: list[dict[str, Any]] = []
    owners: list[tuple[StudyRow, _ArmPlan | None]] = []
    for row, sides, reported in pending:
        if reported is not None:
            items.append(reported)
            owners.append((row, None))
        for plans in sides.values():
            for arm in plans:
                if arm.convert is not None:
                    items.append(arm.convert)
                    owners.append((row, arm))
    if items:
        response = await stats.convert(items)
        for (row, arm), result in zip(owners, response.result["conversions"], strict=True):
            row.conversions.append(
                {
                    k: result.get(k)
                    for k in ("kind", "input", "output", "method", "status", "errors")
                }
            )
            if not result.get("ok"):
                row.reasons.append("conversion_failed")
                continue
            if result.get("status") in ("estimated", "derived"):
                row.flags.append(result["status"])
            elif "converted" not in row.flags:
                row.flags.append("converted")
            if arm is None:
                row.yi, row.vi = result["output"]["yi"], result["output"]["vi"]
            else:
                arm.sd = result["output"]["sd"]
                if "mean" in result["output"]:
                    arm.mean = result["output"]["mean"]

    # 2. Arms of the same group combined (Cochrane formula), then one row per study.
    raw: list[tuple[StudyRow, GroupValues, GroupValues]] = []
    for row, sides, reported in pending:
        if reported is not None or row.reasons:
            continue
        values: list[GroupValues] = []
        for side in ("group1", "group2"):
            plans = sides[side]
            labels = [a.label for a in plans]
            if len(plans) == 1:
                a = plans[0]
                values.append(
                    GroupValues(
                        n=a.n, mean=a.mean, sd=a.sd, events=a.events, total=a.total, arms=labels
                    )
                )
                continue
            row.flags.append("arms_combined")
            spec = (
                {
                    "type": "continuous",
                    "groups": [{"n": a.n, "mean": a.mean, "sd": a.sd} for a in plans],
                }
                if outcome_type == "continuous"
                else {
                    "type": "dichotomous",
                    "groups": [{"events": a.events, "total": a.total} for a in plans],
                }
            )
            combined = await stats.combine_groups(spec)
            if not combined.ok:
                row.reasons.append("combination_failed")
                break
            r = combined.result
            values.append(
                GroupValues(
                    n=r.get("n", r.get("total")),
                    mean=r.get("mean"),
                    sd=r.get("sd"),
                    events=r.get("events"),
                    total=r.get("total"),
                    arms=labels,
                )
            )
        if row.reasons:
            continue
        row.group1, row.group2 = values
        raw.append((row, values[0], values[1]))

    # 3. Effect of each raw study (escalc), with each study's own scale direction.
    if raw:
        cols: dict[str, list[Any]] = {"label": [r.label for r, _, _ in raw]}
        if outcome_type == "continuous":
            cols |= {
                "m1i": [g1.mean for _, g1, _ in raw],
                "sd1i": [g1.sd for _, g1, _ in raw],
                "n1i": [g1.n for _, g1, _ in raw],
                "m2i": [g2.mean for _, _, g2 in raw],
                "sd2i": [g2.sd for _, _, g2 in raw],
                "n2i": [g2.n for _, _, g2 in raw],
                "higher_is_better": [r.higher_is_better is not False for r, _, _ in raw],
            }
        else:
            cols |= {
                "ai": [g1.events for _, g1, _ in raw],
                "n1i": [g1.total for _, g1, _ in raw],
                "ci": [g2.events for _, _, g2 in raw],
                "n2i": [g2.total for _, _, g2 in raw],
            }
        response = await stats.effect_sizes({"measure": measure, "data": cols})
        if not response.ok:
            raise AppError("error.stats_failed", status_code=502)
        for (row, _, _), study in zip(raw, response.result["studies"], strict=True):
            if study.get("yi") is None or not study.get("included", True):
                row.reasons.append(
                    "no_effect_double_zero" if outcome_type != "continuous" else "no_effect"
                )
                continue
            row.yi, row.vi, row.inverted = study["yi"], study["vi"], bool(study.get("inverted"))

    for row, _, _ in pending:
        row.included = not row.reasons and row.yi is not None and row.vi is not None
