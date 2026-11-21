"""Exclusion reasons at full text (docs/modulos.md 7.4; lesson L5).

The list is editable by the admin: reasons nobody used can be removed, used ones can be
renamed or merged into another (decisions move to the reason that stays). Changes are
audited, and a merged reason stays visible as merged (history).
"""

import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ConflictError, ForbiddenError, NotFoundError
from app.modules.projects.access import ProjectContext
from app.modules.screening.models import ExclusionReason, ScreeningDecision, ScreeningResolution

# Standard list (docs/modulos.md 7.4); the screen translates the key while no label is set.
DEFAULTS = (
    "wrong_population",
    "wrong_design",
    "no_comparison_group",
    "no_outcome_data",
    "incompatible_cutoff",
    "duplicate_cohort",
    "full_text_unavailable",
)


class ReasonOut(BaseModel):
    id: uuid.UUID
    key: str | None
    label: str | None
    position: int
    merged_into_id: uuid.UUID | None
    uses: int  # current decisions and resolutions with this reason
    version: int


class ReasonIn(BaseModel):
    label: str = Field(min_length=2, max_length=200)


class ReasonUpdate(BaseModel):
    label: str = Field(min_length=2, max_length=200)
    version: int


class ReasonMergeIn(BaseModel):
    into_id: uuid.UUID
    version: int


def _admin(ctx: ProjectContext) -> None:
    if not ctx.is_admin:
        raise ForbiddenError()


async def _uses(session: AsyncSession, reason_id: uuid.UUID) -> int:
    decisions = await session.scalar(
        select(func.count())
        .select_from(ScreeningDecision)
        .where(
            ScreeningDecision.exclusion_reason_id == reason_id,
            ScreeningDecision.superseded_at.is_(None),
        )
    )
    resolutions = await session.scalar(
        select(func.count())
        .select_from(ScreeningResolution)
        .where(ScreeningResolution.exclusion_reason_id == reason_id)
    )
    return (decisions or 0) + (resolutions or 0)


async def _out(session: AsyncSession, r: ExclusionReason) -> ReasonOut:
    return ReasonOut(
        id=r.id,
        key=r.key,
        label=r.label,
        position=r.position,
        merged_into_id=r.merged_into_id,
        uses=await _uses(session, r.id),
        version=r.version,
    )


async def list_reasons(session: AsyncSession, ctx: ProjectContext) -> list[ReasonOut]:
    """Every reason, merged ones included (they show where they went). The standard list
    is created on first use."""
    rows = list(
        await session.scalars(
            select(ExclusionReason)
            .where(ExclusionReason.project_id == ctx.project.id)
            .order_by(ExclusionReason.position, ExclusionReason.created_at)
        )
    )
    if not rows:
        total = await session.scalar(
            select(func.count())
            .select_from(ExclusionReason)
            .where(ExclusionReason.project_id == ctx.project.id)
            .execution_options(include_deleted=True)
        )
        if not total:  # never seeded (removed reasons are not created again)
            for position, key in enumerate(DEFAULTS):
                session.add(
                    ExclusionReason(
                        project_id=ctx.project.id, key=key, position=position, created_by=None
                    )
                )
            await session.commit()
            return await list_reasons(session, ctx)
    return [await _out(session, r) for r in rows]


async def _get(session: AsyncSession, ctx: ProjectContext, reason_id: uuid.UUID) -> ExclusionReason:
    r = (
        await session.scalars(
            select(ExclusionReason).where(
                ExclusionReason.id == reason_id, ExclusionReason.project_id == ctx.project.id
            )
        )
    ).first()
    if r is None:
        raise NotFoundError()
    return r


async def create(session: AsyncSession, ctx: ProjectContext, data: ReasonIn) -> ReasonOut:
    _admin(ctx)
    await list_reasons(session, ctx)  # seed first, so positions stay in order
    last = await session.scalar(
        select(func.max(ExclusionReason.position)).where(
            ExclusionReason.project_id == ctx.project.id
        )
    )
    r = ExclusionReason(
        project_id=ctx.project.id,
        label=data.label.strip(),
        position=(last or 0) + 1,
        created_by=ctx.user.id,
    )
    session.add(r)
    await session.commit()
    return await _out(session, r)


async def rename(
    session: AsyncSession, ctx: ProjectContext, reason_id: uuid.UUID, data: ReasonUpdate
) -> ReasonOut:
    _admin(ctx)
    r = await _get(session, ctx, reason_id)
    if r.version != data.version:
        raise ConflictError()
    r.label = data.label.strip()
    await session.commit()
    return await _out(session, r)


async def remove(session: AsyncSession, ctx: ProjectContext, reason_id: uuid.UUID) -> None:
    """Only a reason nobody used can be removed (soft delete); used ones are merged."""
    _admin(ctx)
    r = await _get(session, ctx, reason_id)
    in_use = await session.scalar(
        select(func.count())
        .select_from(ScreeningDecision)
        .where(ScreeningDecision.exclusion_reason_id == r.id)
    )
    if in_use or await _uses(session, r.id):
        raise AppError("reason.in_use", status_code=409)
    r.deleted_at = datetime.now(UTC)
    await session.commit()


async def merge(
    session: AsyncSession, ctx: ProjectContext, reason_id: uuid.UUID, data: ReasonMergeIn
) -> ReasonOut:
    """Moves every decision of this reason to `into_id` and marks it as merged."""
    _admin(ctx)
    r = await _get(session, ctx, reason_id)
    target = await _get(session, ctx, data.into_id)
    if r.version != data.version:
        raise ConflictError()
    if target.id == r.id or target.merged_into_id is not None or r.merged_into_id is not None:
        raise AppError("reason.cannot_merge", status_code=409)
    await session.execute(
        update(ScreeningDecision)
        .where(ScreeningDecision.exclusion_reason_id == r.id)
        .values(exclusion_reason_id=target.id)
        .execution_options(synchronize_session=False)
    )
    await session.execute(
        update(ScreeningResolution)
        .where(ScreeningResolution.exclusion_reason_id == r.id)
        .values(exclusion_reason_id=target.id)
        .execution_options(synchronize_session=False)
    )
    r.merged_into_id = target.id
    await session.commit()
    return await _out(session, target)
