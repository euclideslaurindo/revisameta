"""Narrative synthesis (docs/modulos.md 7.7; stage 4 step 4).

The table lists the studies that could not enter the meta-analysis of a result (with
the reasons from the assembly) and the direction of the effect recorded by a reviewer.
The system never infers the direction: a person reads the study and records it (stage 4
decision). Entries of studies that later entered the meta-analysis stay visible, marked,
so nothing disappears in silence.
"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.integrations.stats_client import StatsClient
from app.modules.analysis.assembly import AssemblyIn, assemble
from app.modules.analysis.models import NarrativeEntry
from app.modules.projects.access import ProjectContext
from app.modules.projects.models import Role
from app.modules.studies.models import Study

Direction = Literal[
    "favours_group1", "favours_group2", "no_clear_difference", "mixed", "not_reported"
]
EDITORS = {Role.ADMIN, Role.STATISTICIAN, Role.EXTRACTOR}


class NarrativeRow(BaseModel):
    study_id: uuid.UUID
    label: str
    in_meta_analysis: bool  # an entry of a study that now enters the meta-analysis
    reasons: list[str]
    direction: Direction | None
    note: str | None
    version: int | None
    updated_at: datetime | None


class NarrativeOut(BaseModel):
    outcome_id: uuid.UUID
    outcome_name: str
    timepoint: str
    rows: list[NarrativeRow]
    missing: int  # studies left out with no direction yet


class NarrativeIn(BaseModel):
    outcome_id: uuid.UUID
    timepoint: str = Field(min_length=1, max_length=60)
    direction: Direction
    note: str | None = Field(default=None, max_length=1000)
    version: int | None = None  # the version read; None when creating


async def _entries(
    session: AsyncSession, ctx: ProjectContext, outcome_id: uuid.UUID, timepoint: str
) -> dict[uuid.UUID, NarrativeEntry]:
    rows = await session.scalars(
        select(NarrativeEntry).where(
            NarrativeEntry.project_id == ctx.project.id,
            NarrativeEntry.outcome_id == outcome_id,
            NarrativeEntry.timepoint == timepoint,
        )
    )
    return {e.study_id: e for e in rows}


async def table(
    session: AsyncSession, ctx: ProjectContext, stats: StatsClient, data: AssemblyIn
) -> NarrativeOut:
    out = await assemble(session, ctx, stats, data)
    entries = await _entries(session, ctx, data.outcome_id, data.timepoint)
    rows: list[NarrativeRow] = []
    for s in out.studies:
        e = entries.get(s.study_id)
        if s.included and e is None:
            continue
        rows.append(
            NarrativeRow(
                study_id=s.study_id,
                label=s.label,
                in_meta_analysis=s.included,
                reasons=list(s.reasons),
                direction=e.direction if e else None,
                note=e.note if e else None,
                version=e.version if e else None,
                updated_at=e.updated_at if e else None,
            )
        )
    return NarrativeOut(
        outcome_id=out.outcome_id,
        outcome_name=out.outcome_name,
        timepoint=out.timepoint,
        rows=rows,
        missing=sum(1 for r in rows if not r.in_meta_analysis and r.direction is None),
    )


async def record(
    session: AsyncSession, ctx: ProjectContext, study_id: uuid.UUID, data: NarrativeIn
) -> NarrativeRow:
    if not (EDITORS & ctx.roles):
        raise ForbiddenError()
    study = (
        await session.scalars(
            select(Study).where(Study.id == study_id, Study.project_id == ctx.project.id)
        )
    ).first()
    if study is None:
        raise NotFoundError()
    entry = (await _entries(session, ctx, data.outcome_id, data.timepoint)).get(study_id)
    if entry is None:
        if data.version is not None:
            raise ConflictError()
        entry = NarrativeEntry(
            project_id=ctx.project.id,
            study_id=study_id,
            outcome_id=data.outcome_id,
            timepoint=data.timepoint,
            direction=data.direction,
            note=data.note,
            created_by=ctx.user.id,
        )
        session.add(entry)
    else:
        if data.version != entry.version:
            raise ConflictError()
        entry.direction = data.direction
        entry.note = data.note
    await session.commit()
    await session.refresh(entry)
    return NarrativeRow(
        study_id=study_id,
        label=study.label,
        in_meta_analysis=False,
        reasons=[],
        direction=entry.direction,
        note=entry.note,
        version=entry.version,
        updated_at=entry.updated_at,
    )
