"""Pre-defined analysis plan of the project (docs/modulos.md 7.1 and 7.7; stage 3 step 3).

Stored in `projects.analysis_plan` (JSONB) and validated here:

- comparison: which protocol group is group 1 (experimental/exposed, e.g. "surgery
  before 5 years") and which is group 2 (comparison). The effect is always group 1
  versus group 2.
- cutoff: the cut-off of the question (value and unit) and the rule for studies that
  used another one: "strict" (only the same cut-off) or "tolerant" (cut-offs within a
  range, analysed with a subgroup and a sensitivity analysis by cut-off).
- adjusted: what to do with effects the articles adjusted for confounders:
  "separate" (default: adjusted and unadjusted are never pooled together),
  "adjusted_only" or "unadjusted_only".
- outcomes: per outcome, the measure (or "auto": MD for one scale, SMD for different
  scales; RR for dichotomous) and the time point of the main analysis.
- model: REML with Hartung-Knapp by default (stage 3 decision).
- sensitivity and subgroups planned in advance.

Analyses later compare their settings with this plan: anything different is marked
"not planned" (7.1). Every change is kept in the audit log.
"""

import re
import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ConflictError, ForbiddenError
from app.modules.projects.access import ProjectContext
from app.modules.protocol.models import ComparisonGroup, Outcome

Measure = Literal["auto", "MD", "SMD", "OR", "RR", "RD"]
CONTINUOUS_MEASURES = {"auto", "MD", "SMD"}
DICHOTOMOUS_MEASURES = {"auto", "OR", "RR", "RD"}
SENSITIVITY = (
    "leave_one_out",
    "exclude_high_risk_of_bias",
    "exclude_estimated_data",
    "fixed_vs_random",
    "other_estimator",
    "by_cutoff",
)


class ComparisonPlan(BaseModel):
    group1_id: uuid.UUID
    group2_id: uuid.UUID

    @model_validator(mode="after")
    def _different(self) -> "ComparisonPlan":
        if self.group1_id == self.group2_id:
            raise ValueError("the two groups must be different")
        return self


class CutoffPlan(BaseModel):
    value: float = Field(gt=0, le=1000)
    unit: Literal["years", "months"] = "years"
    rule: Literal["strict", "tolerant"] = "strict"
    tolerance_min: float | None = Field(default=None, gt=0, le=1000)
    tolerance_max: float | None = Field(default=None, gt=0, le=1000)

    @model_validator(mode="after")
    def _range(self) -> "CutoffPlan":
        if self.rule == "tolerant":
            if self.tolerance_min is None or self.tolerance_max is None:
                raise ValueError("a tolerant rule needs the accepted range")
            if not self.tolerance_min <= self.value <= self.tolerance_max:
                raise ValueError("the cut-off of the question must be inside the accepted range")
        else:
            self.tolerance_min = self.tolerance_max = None
        return self


class OutcomePlan(BaseModel):
    outcome_id: uuid.UUID
    measure: Measure = "auto"
    timepoint: str | None = Field(default=None, max_length=60)


class ModelPlan(BaseModel):
    method: Literal["REML", "DL", "PM", "FE"] = "REML"
    test: Literal["knha", "z"] = "knha"

    @model_validator(mode="after")
    def _fixed(self) -> "ModelPlan":
        if self.method == "FE":
            self.test = "z"  # Hartung-Knapp does not apply to a fixed-effect model
        return self


class AnalysisPlan(BaseModel):
    comparison: ComparisonPlan | None = None
    cutoff: CutoffPlan | None = None
    adjusted: Literal["separate", "adjusted_only", "unadjusted_only"] = "separate"
    outcomes: list[OutcomePlan] = Field(default_factory=list, max_length=50)
    model: ModelPlan = Field(default_factory=ModelPlan)
    sensitivity: list[Literal[SENSITIVITY]] = Field(default_factory=list)  # type: ignore[valid-type]
    subgroups: list[str] = Field(default_factory=list, max_length=20)
    notes: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def _unique(self) -> "AnalysisPlan":
        ids = [o.outcome_id for o in self.outcomes]
        if len(ids) != len(set(ids)):
            raise ValueError("each outcome appears once in the plan")
        self.sensitivity = list(dict.fromkeys(self.sensitivity))
        self.subgroups = [s.strip() for s in self.subgroups if s.strip()]
        return self


class PlanIn(AnalysisPlan):
    version: int  # project version (optimistic lock)


class PlanOut(AnalysisPlan):
    version: int
    defined: bool  # False while the group has not saved a plan yet


def current_plan(ctx: ProjectContext) -> AnalysisPlan:
    return AnalysisPlan.model_validate(ctx.project.analysis_plan or {})


def plan_out(ctx: ProjectContext) -> PlanOut:
    plan = current_plan(ctx)
    return PlanOut(
        **plan.model_dump(), version=ctx.project.version, defined=bool(ctx.project.analysis_plan)
    )


async def save_plan(session: AsyncSession, ctx: ProjectContext, data: PlanIn) -> PlanOut:
    if not ctx.is_admin:
        raise ForbiddenError()
    if data.version != ctx.project.version:
        raise ConflictError()
    plan = AnalysisPlan.model_validate(data.model_dump(exclude={"version"}))
    groups = set(
        await session.scalars(
            select(ComparisonGroup.id).where(ComparisonGroup.project_id == ctx.project.id)
        )
    )
    if plan.comparison and not {plan.comparison.group1_id, plan.comparison.group2_id} <= groups:
        raise AppError("plan.unknown_group", status_code=422)
    outcomes = {
        o.id: o
        for o in await session.scalars(select(Outcome).where(Outcome.project_id == ctx.project.id))
    }
    for item in plan.outcomes:
        outcome = outcomes.get(item.outcome_id)
        if outcome is None:
            raise AppError("plan.unknown_outcome", status_code=422)
        allowed = CONTINUOUS_MEASURES if outcome.type == "continuous" else DICHOTOMOUS_MEASURES
        if item.measure not in allowed:
            raise AppError("plan.measure_mismatch", status_code=422, outcome=outcome.name)
        if item.timepoint is not None and item.timepoint not in outcome.timepoints:
            raise AppError("plan.unknown_timepoint", status_code=422, outcome=outcome.name)
    stored: dict[str, Any] = plan.model_dump(mode="json")
    ctx.project.analysis_plan = stored
    await session.commit()
    await session.refresh(ctx.project)
    return plan_out(ctx)


# ---- Cut-off of each study against the plan (used when assembling the analysis) ------

_NUMBER = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*$")

CutoffStatus = Literal["match", "tolerated", "incompatible", "not_numeric", "missing", "no_rule"]


def parse_cutoff(value: Any) -> float | None:
    """A plain number (5, 5.5 or "5,5"); text such as "< 5 years" is never interpreted."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    match = _NUMBER.match(str(value))
    return float(match.group(1).replace(",", ".")) if match else None


def cutoff_status(value: Any, plan: AnalysisPlan) -> CutoffStatus:
    if plan.cutoff is None:
        return "no_rule"
    if value is None or (isinstance(value, str) and not value.strip()):
        return "missing"
    number = parse_cutoff(value)
    if number is None:
        return "not_numeric"
    if number == plan.cutoff.value:
        return "match"
    if (
        plan.cutoff.rule == "tolerant"
        and plan.cutoff.tolerance_min is not None
        and plan.cutoff.tolerance_max is not None
        and plan.cutoff.tolerance_min <= number <= plan.cutoff.tolerance_max
    ):
        return "tolerated"
    return "incompatible"
