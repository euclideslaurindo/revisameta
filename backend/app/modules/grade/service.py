"""GRADE certainty of the evidence (docs/modulos.md 7.8; stage 6 step 1).

The system runs the analysis of a result (same assembly and model as the meta-analysis
screen) and suggests, for each reason to rate down or up, a change with the reason it
was suggested. The thresholds were approved by the group and can be changed per
project. People decide: every change that is not zero, and every choice that differs
from the suggestion, needs a justification. No statistic is computed here: the
numbers come from the R service and are only compared with the thresholds.
"""

import math
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ConflictError, ForbiddenError, NotFoundError
from app.integrations.stats_client import StatsClient
from app.modules.analysis.publication_bias import egger
from app.modules.analysis.run import RunIn, RunOut, run
from app.modules.grade.models import GradeAssessment
from app.modules.projects.access import ProjectContext
from app.modules.projects.models import Role
from app.modules.protocol.models import Outcome
from app.modules.risk_of_bias.consolidated import table as rob_table
from app.modules.studies.models import Study, StudyDesign

EDITORS = {Role.ADMIN, Role.REVIEWER, Role.STATISTICIAN}
LEVELS = ["very_low", "low", "moderate", "high"]
DOWN = ["risk_of_bias", "inconsistency", "indirectness", "imprecision", "publication_bias"]
UP = ["large_effect", "dose_response", "plausible_confounding"]
LIMITS: dict[str, tuple[int, int]] = {
    **{k: (-2, 0) for k in DOWN},
    "large_effect": (0, 2),
    "dose_response": (0, 1),
    "plausible_confounding": (0, 1),
}
HIGH_RISK = {"high", "serious", "critical", "very_high", "poor"}
RATIO = {"OR", "RR"}

Approach = Literal["classic", "robins_i"]
Certainty = Literal["very_low", "low", "moderate", "high"]


class GradeSettings(BaseModel):
    """Approved defaults (docs/roteiro.md, stage 6)."""

    i2_threshold: float = Field(default=50, ge=0, le=100)  # I² at or above: inconsistency
    high_risk_share: float = Field(default=0.5, ge=0, le=1)  # more than this share: RoB
    egger_p: float = Field(default=0.10, gt=0, lt=1)  # Egger p below: publication bias
    egger_min_k: int = Field(default=10, ge=3)  # Egger only with this many studies
    large_ratio: float = Field(default=2, gt=1)  # RR/OR at or above (or 1/x below)


class GradeBasis(RunIn):
    rob_tool_id: uuid.UUID | None = None


class DomainSuggestion(BaseModel):
    suggested: int
    reason: str  # code shown by the screen (i18n)
    values: dict[str, Any] = Field(default_factory=dict)


class SuggestOut(BaseModel):
    outcome_id: uuid.UUID
    timepoint: str
    measure: str
    method: str
    test: str
    k: int
    participants: int | None
    estimate: float | None
    ci_lb: float | None
    ci_ub: float | None
    ratio: bool  # estimate and CI on the log scale
    i2: float | None
    observational: bool
    start_suggested: Certainty
    domains: dict[str, DomainSuggestion]


class DomainIn(BaseModel):
    change: int
    justification: str | None = Field(default=None, max_length=2000)


class GradeIn(GradeBasis):
    approach: Approach
    start_certainty: Literal["low", "high"]
    domains: dict[str, DomainIn]
    note: str | None = Field(default=None, max_length=2000)
    version: int | None = None


class GradeOut(BaseModel):
    id: uuid.UUID
    outcome_id: uuid.UUID
    outcome_name: str
    timepoint: str
    approach: str
    start_certainty: str
    final_certainty: str
    analysis: dict[str, Any]
    domains: dict[str, Any]
    suggestions: dict[str, Any]
    summary: dict[str, Any]
    note: str | None
    version: int


def settings_of(ctx: ProjectContext) -> GradeSettings:
    return GradeSettings.model_validate(ctx.project.grade_settings or {})


async def update_settings(
    session: AsyncSession, ctx: ProjectContext, data: GradeSettings
) -> GradeSettings:
    if not ctx.is_admin:
        raise ForbiddenError()
    ctx.project.grade_settings = data.model_dump()
    await session.commit()
    return data


def final_certainty(start: str, domains: dict[str, int]) -> str:
    """Start level, minus the downgrades, plus the upgrades, kept within the scale."""
    level = LEVELS.index(start) + sum(domains.values())
    return LEVELS[max(0, min(len(LEVELS) - 1, level))]


async def _participants(main: RunOut) -> int | None:
    total = 0
    for s in main.assembly.studies:
        if not s.included:
            continue
        for g in (s.group1, s.group2):
            if g is None or g.n is None:
                return None
            total += int(g.n)
    return total


async def _observational(session: AsyncSession, ctx: ProjectContext, ids: list[uuid.UUID]) -> bool:
    designs = set(
        await session.scalars(
            select(Study.design).where(Study.project_id == ctx.project.id, Study.id.in_(ids))
        )
    )
    return designs != {StudyDesign.RCT.value}


async def _rob(
    session: AsyncSession,
    ctx: ProjectContext,
    data: GradeBasis,
    ids: list[uuid.UUID],
    cfg: GradeSettings,
) -> DomainSuggestion:
    if data.rob_tool_id is None:
        return DomainSuggestion(suggested=0, reason="rob_no_tool")
    table = await rob_table(session, ctx, data.rob_tool_id, data.outcome_id, data.timepoint)
    overall = {r.study_id: r.overall for r in table.rows}
    judged = [overall.get(i) for i in ids]
    missing = sum(1 for j in judged if j is None)
    high = sum(1 for j in judged if j in HIGH_RISK)
    values = {"high": high, "k": len(ids), "missing": missing}
    if ids and high / len(ids) > cfg.high_risk_share:
        return DomainSuggestion(suggested=-1, reason="rob_many_high", values=values)
    if missing:
        return DomainSuggestion(suggested=0, reason="rob_missing", values=values)
    return DomainSuggestion(suggested=0, reason="rob_ok", values=values)


async def suggest(
    session: AsyncSession, ctx: ProjectContext, stats: StatsClient, data: GradeBasis
) -> SuggestOut:
    cfg = settings_of(ctx)
    main = await run(session, ctx, stats, data)
    pooled = main.result.get("pooled", {})
    het = main.result.get("heterogeneity", {})
    included = [s for s in main.assembly.studies if s.included]
    ids = [s.study_id for s in included]
    measure = main.assembly.measure
    ratio = measure in RATIO
    estimate, lb, ub = pooled.get("estimate"), pooled.get("ci_lb"), pooled.get("ci_ub")
    i2 = het.get("i2")
    domains: dict[str, DomainSuggestion] = {}

    domains["risk_of_bias"] = await _rob(session, ctx, data, ids, cfg)

    if i2 is None or main.result.get("k", 0) < 2 or main.method == "FE":
        domains["inconsistency"] = DomainSuggestion(suggested=0, reason="inconsistency_no_data")
    elif i2 >= cfg.i2_threshold:
        domains["inconsistency"] = DomainSuggestion(
            suggested=-1, reason="inconsistency_high_i2", values={"i2": i2}
        )
    else:
        domains["inconsistency"] = DomainSuggestion(
            suggested=0, reason="inconsistency_ok", values={"i2": i2}
        )

    tolerated = [s.label for s in included if "cutoff_tolerated" in s.flags]
    domains["indirectness"] = (
        DomainSuggestion(
            suggested=-1, reason="indirectness_cutoff", values={"studies": ", ".join(tolerated)}
        )
        if tolerated
        else DomainSuggestion(suggested=0, reason="indirectness_ok")
    )

    # The null is 0 for differences and for ratios on the log scale.
    crosses = lb is not None and ub is not None and lb < 0 < ub
    domains["imprecision"] = DomainSuggestion(
        suggested=-1 if crosses else 0,
        reason="imprecision_crosses_null" if crosses else "imprecision_ok",
    )

    if len(ids) < cfg.egger_min_k:
        domains["publication_bias"] = DomainSuggestion(
            suggested=0,
            reason="publication_bias_few",
            values={"k": len(ids), "min": cfg.egger_min_k},
        )
    else:
        test = await egger(session, ctx, stats, data)
        p = test.result.get("p_value")
        low = p is not None and p < cfg.egger_p
        domains["publication_bias"] = DomainSuggestion(
            suggested=-1 if low else 0,
            reason="publication_bias_egger" if low else "publication_bias_ok",
            values={"p": p},
        )

    downgraded = any(d.suggested < 0 for d in domains.values())
    limit = math.log(cfg.large_ratio)  # thresholds compared on the scale R returns
    large = ratio and estimate is not None and abs(estimate) >= limit and not downgraded
    domains["large_effect"] = DomainSuggestion(
        suggested=1 if large else 0,
        reason="large_effect"
        if large
        else ("large_effect_ratio_only" if not ratio else "large_effect_no"),
    )
    domains["dose_response"] = DomainSuggestion(suggested=0, reason="human_only")
    domains["plausible_confounding"] = DomainSuggestion(suggested=0, reason="human_only")

    observational = await _observational(session, ctx, ids)
    return SuggestOut(
        outcome_id=data.outcome_id,
        timepoint=data.timepoint,
        measure=measure,
        method=main.method,
        test=main.test,
        k=len(ids),
        participants=await _participants(main),
        estimate=estimate,
        ci_lb=lb,
        ci_ub=ub,
        ratio=ratio,
        i2=i2,
        observational=observational,
        start_suggested="low" if observational else "high",
        domains=domains,
    )


async def _outcome_names(session: AsyncSession, ctx: ProjectContext) -> dict[uuid.UUID, str]:
    rows = await session.execute(
        select(Outcome.id, Outcome.name).where(Outcome.project_id == ctx.project.id)
    )
    return {i: n for i, n in rows.all()}


def _out(a: GradeAssessment, names: dict[uuid.UUID, str]) -> GradeOut:
    return GradeOut(
        id=a.id,
        outcome_id=a.outcome_id,
        outcome_name=names.get(a.outcome_id, ""),
        timepoint=a.timepoint,
        approach=a.approach,
        start_certainty=a.start_certainty,
        final_certainty=a.final_certainty,
        analysis=a.analysis,
        domains=a.domains,
        suggestions=a.suggestions,
        summary=a.summary,
        note=a.note,
        version=a.version,
    )


async def assessments(session: AsyncSession, ctx: ProjectContext) -> list[GradeOut]:
    names = await _outcome_names(session, ctx)
    rows = await session.scalars(
        select(GradeAssessment)
        .where(GradeAssessment.project_id == ctx.project.id)
        .order_by(GradeAssessment.created_at)
    )
    return [_out(a, names) for a in rows]


async def save(
    session: AsyncSession, ctx: ProjectContext, stats: StatsClient, data: GradeIn
) -> GradeOut:
    if not (EDITORS & ctx.roles):
        raise ForbiddenError()
    if set(data.domains) != set(LIMITS):
        raise AppError("grade.domains_missing", status_code=422)
    found = await suggest(session, ctx, stats, data)
    domains: dict[str, Any] = {}
    for key, item in data.domains.items():
        low, high = LIMITS[key]
        if not low <= item.change <= high:
            raise AppError("grade.change_out_of_range", status_code=422, domain=key)
        text = (item.justification or "").strip()
        if (item.change != 0 or item.change != found.domains[key].suggested) and not text:
            raise AppError("grade.justification_required", status_code=422, domain=key)
        domains[key] = {"change": item.change, "justification": text or None}
    final = final_certainty(data.start_certainty, {k: v["change"] for k, v in domains.items()})
    basis = GradeBasis.model_validate(data.model_dump()).model_dump(mode="json")
    summary = found.model_dump(mode="json", exclude={"domains"})
    suggestions = {k: v.model_dump() for k, v in found.domains.items()}
    row = (
        await session.scalars(
            select(GradeAssessment).where(
                GradeAssessment.project_id == ctx.project.id,
                GradeAssessment.outcome_id == data.outcome_id,
                GradeAssessment.timepoint == data.timepoint,
            )
        )
    ).first()
    if row is None:
        if data.version is not None:
            raise ConflictError()
        row = GradeAssessment(
            project_id=ctx.project.id,
            outcome_id=data.outcome_id,
            timepoint=data.timepoint,
            created_by=ctx.user.id,
        )
        session.add(row)
    elif data.version != row.version:
        raise ConflictError()
    row.approach, row.start_certainty, row.final_certainty = (
        data.approach,
        data.start_certainty,
        final,
    )
    row.analysis, row.domains, row.suggestions, row.summary = basis, domains, suggestions, summary
    row.note = (data.note or "").strip() or None
    await session.commit()
    await session.refresh(row)
    return _out(row, await _outcome_names(session, ctx))


async def delete(session: AsyncSession, ctx: ProjectContext, assessment_id: uuid.UUID) -> None:
    """Soft delete: the judgement leaves the list but stays in the database."""
    if not (EDITORS & ctx.roles):
        raise ForbiddenError()
    row = (
        await session.scalars(
            select(GradeAssessment).where(
                GradeAssessment.id == assessment_id, GradeAssessment.project_id == ctx.project.id
            )
        )
    ).first()
    if row is None:
        raise NotFoundError()
    row.deleted_at = datetime.now(UTC)
    await session.commit()
