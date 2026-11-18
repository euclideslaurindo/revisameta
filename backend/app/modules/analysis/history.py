"""History of analyses (docs/modulos.md 7.7 "Reprodutibilidade"; stage 3 step 7).

- Saving keeps the exact data that entered (yi/vi per study and the trail of what was
  done to each study's numbers), the parameters, the result, the R and package
  versions, the date and the author.
- An analysis becomes "outdated" when the data behind it change: a consensus number
  is corrected (data_version goes up), a consensus is reopened, or a study gains or
  loses its consensus. It is never recomputed silently; the user runs it again.
- The R script is written by the R service from the saved data and reproduces the
  result in a clean R session.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ForbiddenError, NotFoundError
from app.integrations.stats_client import StatsClient
from app.modules.analysis.models import Analysis
from app.modules.analysis.run import RunIn, run
from app.modules.auth.models import User
from app.modules.exports.extraction import _slug
from app.modules.extraction.models import Extraction
from app.modules.projects.access import ProjectContext
from app.modules.projects.models import Role
from app.modules.studies.models import Study


class SaveIn(RunIn):
    note: str | None = Field(default=None, max_length=500)


class AnalysisSummary(BaseModel):
    id: uuid.UUID
    outcome_id: uuid.UUID
    outcome_name: str
    timepoint: str
    measure: str
    method: str
    test: str
    data_set: str
    k: int
    planned: bool
    not_planned: list[str]
    estimate: float | None
    ci_lb: float | None
    ci_ub: float | None
    i2: float | None
    note: str | None
    created_at: datetime
    created_by_name: str | None
    outdated: bool
    outdated_reasons: list[str]  # data_changed | studies_changed


class AnalysisOut(AnalysisSummary):
    input_snapshot: dict[str, Any]
    result: dict[str, Any]
    warnings: list[str]
    r_meta: dict[str, Any]


def _can_save(ctx: ProjectContext) -> None:
    if not ({Role.ADMIN, Role.STATISTICIAN} & ctx.roles):
        raise ForbiddenError()


async def current_sources(session: AsyncSession, ctx: ProjectContext) -> dict[str, Any]:
    """Consensus extraction, data version and status of every study of the project."""
    studies = list(
        await session.scalars(select(Study.id).where(Study.project_id == ctx.project.id))
    )
    consensus = {
        e.study_id: e
        for e in await session.scalars(
            select(Extraction).where(
                Extraction.project_id == ctx.project.id, Extraction.kind == "consensus"
            )
        )
    }
    out: dict[str, Any] = {}
    for study_id in studies:
        e = consensus.get(study_id)
        final = e is not None and e.status in ("submitted", "locked")
        out[str(study_id)] = {
            "extraction_id": str(e.id) if final and e else None,
            "data_version": e.data_version if final and e else None,
        }
    return out


def _outdated(saved: dict[str, Any], current: dict[str, Any], included: list[str]) -> list[str]:
    reasons: list[str] = []
    for study_id, now in current.items():
        then = saved.get(study_id, {"extraction_id": None, "data_version": None})
        if then == now:
            continue
        if (
            study_id in included
            and then.get("extraction_id")
            and now.get("extraction_id") == then.get("extraction_id")
        ):
            reasons.append("data_changed")
        else:
            reasons.append("studies_changed")
    for study_id in saved:
        if study_id not in current and study_id in included:
            reasons.append("studies_changed")
    return sorted(set(reasons))


async def _names(session: AsyncSession, ids: set[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    real = {i for i in ids if i}
    if not real:
        return {}
    return {u.id: u.name for u in await session.scalars(select(User).where(User.id.in_(real)))}


def _summary(a: Analysis, names: dict[uuid.UUID, str], current: dict[str, Any]) -> AnalysisSummary:
    pooled = (a.result or {}).get("pooled", {})
    het = (a.result or {}).get("heterogeneity", {})
    reasons = _outdated(a.sources or {}, current, a.included_study_ids or [])
    return AnalysisSummary(
        id=a.id,
        outcome_id=a.outcome_id,
        outcome_name=a.input_snapshot.get("outcome_name", ""),
        timepoint=a.timepoint,
        measure=a.measure,
        method=a.method,
        test=a.test,
        data_set=a.data_set,
        k=a.k,
        planned=a.planned,
        not_planned=a.not_planned or [],
        estimate=pooled.get("estimate"),
        ci_lb=pooled.get("ci_lb"),
        ci_ub=pooled.get("ci_ub"),
        i2=het.get("i2"),
        note=a.note,
        created_at=a.created_at,
        created_by_name=names.get(a.created_by) if a.created_by else None,
        outdated=bool(reasons),
        outdated_reasons=reasons,
    )


async def save(
    session: AsyncSession, ctx: ProjectContext, stats: StatsClient, data: SaveIn
) -> AnalysisOut:
    _can_save(ctx)
    out = await run(session, ctx, stats, data)
    assembly = out.assembly
    snapshot = {
        **assembly.model_dump(mode="json"),
        "group1_label": out.group1_label,
        "group2_label": out.group2_label,
        "favours_right": out.favours_right,
    }
    analysis = Analysis(
        project_id=ctx.project.id,
        created_by=ctx.user.id,
        outcome_id=assembly.outcome_id,
        timepoint=assembly.timepoint,
        measure=assembly.measure,
        method=out.method,
        test=out.test,
        data_set=assembly.data_set,
        k=assembly.k,
        planned=not out.not_planned,
        not_planned=out.not_planned,
        included_study_ids=[str(s.study_id) for s in assembly.studies if s.included],
        input_snapshot=snapshot,
        sources=await current_sources(session, ctx),
        result=out.result,
        warnings=out.warnings,
        r_meta=out.r_meta,
        note=(data.note or "").strip() or None,
    )
    session.add(analysis)
    await session.commit()
    return await detail(session, ctx, analysis.id)


async def _get(session: AsyncSession, ctx: ProjectContext, analysis_id: uuid.UUID) -> Analysis:
    a = (
        await session.scalars(
            select(Analysis).where(
                Analysis.id == analysis_id, Analysis.project_id == ctx.project.id
            )
        )
    ).first()
    if a is None:
        raise NotFoundError()
    return a


async def history(session: AsyncSession, ctx: ProjectContext) -> list[AnalysisSummary]:
    rows = list(
        await session.scalars(
            select(Analysis)
            .where(Analysis.project_id == ctx.project.id)
            .order_by(Analysis.created_at.desc())
        )
    )
    names = await _names(session, {a.created_by for a in rows})
    current = await current_sources(session, ctx)
    return [_summary(a, names, current) for a in rows]


async def detail(session: AsyncSession, ctx: ProjectContext, analysis_id: uuid.UUID) -> AnalysisOut:
    a = await _get(session, ctx, analysis_id)
    names = await _names(session, {a.created_by})
    summary = _summary(a, names, await current_sources(session, ctx))
    return AnalysisOut(
        **summary.model_dump(),
        input_snapshot=a.input_snapshot,
        result=a.result,
        warnings=a.warnings or [],
        r_meta=a.r_meta,
    )


async def delete(session: AsyncSession, ctx: ProjectContext, analysis_id: uuid.UUID) -> None:
    """Soft delete (never erased): it leaves the history but stays in the database."""
    _can_save(ctx)
    a = await _get(session, ctx, analysis_id)
    a.deleted_at = datetime.now(UTC)
    await session.commit()


async def r_script(
    session: AsyncSession, ctx: ProjectContext, stats: StatsClient, analysis_id: uuid.UUID
) -> tuple[str, str]:
    """A .R file that reproduces the saved analysis in a clean R session."""
    a = await _get(session, ctx, analysis_id)
    snap = a.input_snapshot
    request = snap.get("request") or {}
    included = [s for s in snap.get("studies", []) if s.get("included")]
    notes = []
    for s in included:
        methods = [c.get("method") for c in s.get("conversions", []) if c.get("method")]
        extra = []
        if s.get("inverted"):
            extra.append("sign inverted (higher is worse)")
        if methods:
            extra.append("; ".join(dict.fromkeys(methods)))
        if extra:
            notes.append(f"{s['label']}: {' | '.join(extra)}")
    spec = {
        "measure": a.measure,
        "method": a.method,
        "test": a.test,
        "data": request.get("data", {}),
        "info": {
            "project": ctx.project.title,
            "outcome": snap.get("outcome_name", ""),
            "timepoint": a.timepoint,
            "data_set": a.data_set,
            "analysis_id": str(a.id),
            "saved_at": a.created_at.isoformat(),
            "r_version": (a.r_meta or {}).get("r_version"),
            "metafor_version": ((a.r_meta or {}).get("packages") or {}).get("metafor"),
            "group1": snap.get("group1_label"),
            "group2": snap.get("group2_label"),
            "notes": notes,
        },
    }
    response = await stats.r_script(spec)
    if not response.ok:
        raise AppError("error.stats_failed", status_code=502)
    day = a.created_at.strftime("%Y-%m-%d")
    name = f"{_slug(ctx.project.title)}_meta-analise_{_slug(snap.get('outcome_name', ''))}_{day}.R"
    return str(response.result["script"]), name
