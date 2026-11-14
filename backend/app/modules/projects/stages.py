"""Locked stages (docs/modulos.md, 7.12): a locked stage refuses every change.

The admin locks a stage once its review is complete (for extraction: the final
review, block F of 7.5.1). Unlocking needs a justification, kept in
`stage_events` together with every lock and reopen.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.modules.auth.models import User
from app.modules.projects.access import ProjectContext
from app.modules.projects.models import Stage, StageAction, StageEvent


class StageEventOut(BaseModel):
    action: str
    target_id: uuid.UUID | None
    justification: str | None
    user_name: str | None
    created_at: datetime


def is_locked(ctx: ProjectContext, stage: Stage) -> bool:
    return str(stage) in (ctx.project.locked_stages or [])


def ensure_open(ctx: ProjectContext, stage: Stage) -> None:
    """Every write of a stage calls this first."""
    if is_locked(ctx, stage):
        raise AppError("stage.locked", status_code=409, stage=str(stage))


def record(
    session: AsyncSession,
    ctx: ProjectContext,
    stage: Stage,
    action: StageAction,
    justification: str | None = None,
    target_id: uuid.UUID | None = None,
) -> None:
    session.add(
        StageEvent(
            project_id=ctx.project.id,
            created_by=ctx.user.id,
            stage=stage,
            action=action,
            target_id=target_id,
            justification=justification,
            user_id=ctx.user.id,
        )
    )


def set_locked(ctx: ProjectContext, stage: Stage, locked: bool) -> None:
    current = [s for s in (ctx.project.locked_stages or []) if s != str(stage)]
    # A new list, so the change is detected (and audited) by the ORM.
    ctx.project.locked_stages = [*current, str(stage)] if locked else current


async def events(session: AsyncSession, ctx: ProjectContext, stage: Stage) -> list[StageEventOut]:
    rows = list(
        await session.scalars(
            select(StageEvent)
            .where(StageEvent.project_id == ctx.project.id, StageEvent.stage == str(stage))
            .order_by(StageEvent.created_at.desc())
        )
    )
    ids = {r.user_id for r in rows}
    names = (
        {u.id: u.name for u in await session.scalars(select(User).where(User.id.in_(ids)))}
        if ids
        else {}
    )
    return [
        StageEventOut(
            action=r.action,
            target_id=r.target_id,
            justification=r.justification,
            user_name=names.get(r.user_id),
            created_at=r.created_at,
        )
        for r in rows
    ]
