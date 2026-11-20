"""Subgroup analysis (docs/modulos.md 7.7; stage 4 step 2).

The study's subgroup comes from:
- characteristic: a field of the consensus extraction form (e.g. type of surgery);
- risk_of_bias: the final overall judgement for this result (consensus or import);
- cutoff: the cut-off the study used (useful with the plan's tolerant rule).
Studies without a value are left out and listed. The R service fits one model per
subgroup (own tau^2) and the test for subgroup differences (stage 4 decision).
"""

from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.integrations.stats_client import StatsClient
from app.modules.analysis.run import RunIn, run
from app.modules.analysis.sensitivity import _risk_levels
from app.modules.extraction.models import Extraction
from app.modules.projects.access import ProjectContext
from app.modules.protocol.analysis_plan import current_plan, parse_cutoff


class SubgroupIn(RunIn):
    variable: Literal["characteristic", "risk_of_bias", "cutoff"]
    key: str | None = Field(default=None, max_length=80)  # the form field, for "characteristic"
    label: str | None = Field(default=None, max_length=200)  # how the screen names it


class SubgroupOut(BaseModel):
    variable: str
    key: str | None
    planned: bool
    measure: str
    groups: dict[str, str]  # study label -> subgroup
    left_out: list[str]  # studies in the analysis without a value for the variable
    result: dict[str, Any]  # subgroups and the test of differences, from R
    warnings: list[str]


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        value = ", ".join(str(v) for v in value if v not in (None, ""))
    text = str(value).strip()
    return text or None


async def subgroups(
    session: AsyncSession, ctx: ProjectContext, stats: StatsClient, data: SubgroupIn
) -> SubgroupOut:
    if data.variable == "characteristic" and not data.key:
        raise AppError("analysis.subgroup_key_required", status_code=422)
    main = await run(session, ctx, stats, data)
    included = [s for s in main.assembly.studies if s.included]
    groups: dict[str, str | None] = {}
    if data.variable == "risk_of_bias":
        levels = await _risk_levels(session, ctx, main)
        groups = {label: final for label, (final, _) in levels.items()}
    else:
        consensus = {
            e.study_id: e
            for e in await session.scalars(
                select(Extraction).where(
                    Extraction.project_id == ctx.project.id,
                    Extraction.kind == "consensus",
                    Extraction.study_id.in_([s.study_id for s in included]),
                )
            )
        }
        for s in included:
            e = consensus.get(s.study_id)
            chars = (e.characteristics or {}) if e else {}
            if data.variable == "cutoff":
                number = parse_cutoff(chars.get("cutoff_used"))
                groups[s.label] = None if number is None else f"{number:g}"
            else:
                groups[s.label] = _text(chars.get(data.key or ""))
    request = main.assembly.request or {}
    payload = request.get("data", {})
    labels: list[str] = payload.get("label", [])
    response = await stats.subgroup(
        {
            **request,
            "method": main.method,
            "test": main.test,
            "data": {**payload, "group": [groups.get(label) for label in labels]},
        }
    )
    if not response.ok:
        raise AppError("analysis.subgroup_needs_two", status_code=409)
    plan = current_plan(ctx)
    names = {n.strip().lower() for n in plan.subgroups}
    candidates = {(data.key or "").lower(), (data.label or "").lower(), data.variable}
    return SubgroupOut(
        variable=data.variable,
        key=data.key,
        planned=bool(names & {c for c in candidates if c}),
        measure=main.assembly.measure,
        groups={k: v for k, v in groups.items() if v is not None},
        left_out=[label for label in labels if groups.get(label) is None],
        result=response.result,
        warnings=list(dict.fromkeys(response.warnings)),
    )
