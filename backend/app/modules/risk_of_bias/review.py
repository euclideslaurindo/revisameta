"""Review and lock of the risk-of-bias stage (docs/modulos.md 7.6 and 7.12, stage 2 step 7).

- The review lists every study: its instrument and, for each study or result assessed,
  where it stands. Nothing is half done when the stage locks: every study has a
  confirmed instrument and at least one final assessment (submitted consensus or
  import), and no assessment is still in progress.
- Locking freezes every write of the stage (`ensure_open`). Unlocking needs a
  justification, kept in the stage history with every lock and reopen.
- With the stage open, an admin can reopen a submitted consensus to correct it, or
  discard an import (soft delete) to import it again; both need a justification.
"""

import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ForbiddenError, NotFoundError
from app.modules.projects.access import ProjectContext
from app.modules.projects.models import Stage, StageAction
from app.modules.projects.stages import (
    StageEventOut,
    ensure_open,
    events,
    is_locked,
    record,
    set_locked,
)
from app.modules.protocol.models import Outcome
from app.modules.risk_of_bias import assessments as asm
from app.modules.risk_of_bias.models import RobAssessment, RobStudyTool, RobTool
from app.modules.studies.models import Study

FINAL_KINDS = ("consensus", "imported")


class JustificationIn(BaseModel):
    justification: str = Field(min_length=5, max_length=1000)


class TargetState(BaseModel):
    outcome_id: uuid.UUID | None
    outcome_name: str | None
    timepoint: str | None
    # done | consensus_pending | in_progress
    state: str
    final_id: uuid.UUID | None
    final_kind: str | None


class StudyReview(BaseModel):
    study_id: uuid.UUID
    label: str
    tool_id: uuid.UUID | None
    tool_key: str | None
    tool_version: str | None
    tool_name: dict[str, str] | None
    targets: list[TargetState]
    # ready | no_tool | no_assessment | in_progress
    state: str


class RobReviewOut(BaseModel):
    locked: bool
    total: int
    ready: int
    can_lock: bool
    studies: list[StudyReview]
    history: list[StageEventOut]


def _require_admin(ctx: ProjectContext) -> None:
    if not ctx.is_admin:
        raise ForbiddenError()


async def review(session: AsyncSession, ctx: ProjectContext) -> RobReviewOut:
    studies = list(
        await session.scalars(
            select(Study)
            .where(Study.project_id == ctx.project.id, Study.deleted_at.is_(None))
            .order_by(Study.label)
        )
    )
    choices = {
        c.study_id: c.tool_id
        for c in await session.scalars(
            select(RobStudyTool).where(RobStudyTool.project_id == ctx.project.id)
        )
    }
    tools = {
        t.id: t
        for t in await session.scalars(select(RobTool).where(RobTool.project_id == ctx.project.id))
    }
    outcomes = {
        o.id: o.name
        for o in await session.scalars(select(Outcome).where(Outcome.project_id == ctx.project.id))
    }
    assessments = list(
        await session.scalars(
            select(RobAssessment)
            .where(RobAssessment.project_id == ctx.project.id)
            .order_by(RobAssessment.created_at)
        )
    )
    out: list[StudyReview] = []
    for study in studies:
        tool_id = choices.get(study.id)
        tool = tools.get(tool_id) if tool_id else None
        mine = [a for a in assessments if a.study_id == study.id and a.tool_id == tool_id]
        targets: list[TargetState] = []
        for outcome_id, timepoint in dict.fromkeys((a.outcome_id, a.timepoint) for a in mine):
            group = [a for a in mine if (a.outcome_id, a.timepoint) == (outcome_id, timepoint)]
            final = next((a for a in group if a.kind in FINAL_KINDS and a.status != "draft"), None)
            draft_final = any(a.kind == "consensus" and a.status == "draft" for a in group)
            individuals = [a for a in group if a.kind == "individual"]
            if final is not None:
                state = "done"
            elif draft_final or len(
                [a for a in individuals if a.status != "draft"]
            ) >= asm.reviewers_needed(ctx):
                state = "consensus_pending"
            else:
                state = "in_progress"
            targets.append(
                TargetState(
                    outcome_id=outcome_id,
                    outcome_name=outcomes.get(outcome_id) if outcome_id else None,
                    timepoint=timepoint,
                    state=state,
                    final_id=final.id if final else None,
                    final_kind=final.kind if final else None,
                )
            )
        if tool is None:
            study_state = "no_tool"
        elif not targets:
            study_state = "no_assessment"
        elif any(t.state != "done" for t in targets):
            study_state = "in_progress"
        else:
            study_state = "ready"
        out.append(
            StudyReview(
                study_id=study.id,
                label=study.label,
                tool_id=tool.id if tool else None,
                tool_key=tool.template_key if tool else None,
                tool_version=tool.template_version if tool else None,
                tool_name=tool.structure.get("name") if tool else None,
                targets=targets,
                state=study_state,
            )
        )
    ready = len([s for s in out if s.state == "ready"])
    locked = is_locked(ctx, Stage.RISK_OF_BIAS)
    return RobReviewOut(
        locked=locked,
        total=len(out),
        ready=ready,
        can_lock=not locked and bool(out) and ready == len(out),
        studies=out,
        history=await events(session, ctx, Stage.RISK_OF_BIAS),
    )


async def _finals(session: AsyncSession, ctx: ProjectContext) -> list[RobAssessment]:
    return list(
        await session.scalars(
            select(RobAssessment).where(
                RobAssessment.project_id == ctx.project.id,
                RobAssessment.kind.in_(FINAL_KINDS),
            )
        )
    )


async def lock(session: AsyncSession, ctx: ProjectContext) -> RobReviewOut:
    _require_admin(ctx)
    ensure_open(ctx, Stage.RISK_OF_BIAS)
    current = await review(session, ctx)
    if not current.can_lock:
        raise AppError(
            "rob.review_not_ready", status_code=409, ready=current.ready, total=current.total
        )
    for a in await _finals(session, ctx):
        if a.status == "submitted":
            a.status = "locked"
    set_locked(ctx, Stage.RISK_OF_BIAS, True)
    record(session, ctx, Stage.RISK_OF_BIAS, StageAction.LOCK)
    await session.commit()
    return await review(session, ctx)


async def unlock(session: AsyncSession, ctx: ProjectContext, data: JustificationIn) -> RobReviewOut:
    _require_admin(ctx)
    if not is_locked(ctx, Stage.RISK_OF_BIAS):
        raise AppError("stage.not_locked", status_code=409)
    for a in await _finals(session, ctx):
        if a.status == "locked":
            a.status = "submitted"
    set_locked(ctx, Stage.RISK_OF_BIAS, False)
    record(session, ctx, Stage.RISK_OF_BIAS, StageAction.UNLOCK, data.justification.strip())
    await session.commit()
    return await review(session, ctx)


async def _final(
    session: AsyncSession, ctx: ProjectContext, assessment_id: uuid.UUID
) -> RobAssessment:
    a = (
        await session.scalars(
            select(RobAssessment).where(
                RobAssessment.id == assessment_id,
                RobAssessment.project_id == ctx.project.id,
                RobAssessment.kind.in_(FINAL_KINDS),
            )
        )
    ).first()
    if a is None:
        raise NotFoundError()
    return a


async def reopen(
    session: AsyncSession, ctx: ProjectContext, assessment_id: uuid.UUID, data: JustificationIn
) -> RobReviewOut:
    """Puts a submitted consensus back to draft to correct it (justified)."""
    _require_admin(ctx)
    ensure_open(ctx, Stage.RISK_OF_BIAS)
    a = await _final(session, ctx, assessment_id)
    if a.kind != "consensus":
        raise AppError("rob.reopen_only_consensus", status_code=409)
    if a.status != "submitted":
        raise AppError("rob.not_submitted", status_code=409)
    a.status = "draft"
    a.submitted_by = None
    a.submitted_at = None
    record(session, ctx, Stage.RISK_OF_BIAS, StageAction.REOPEN, data.justification.strip(), a.id)
    await session.commit()
    return await review(session, ctx)


async def discard_import(
    session: AsyncSession, ctx: ProjectContext, assessment_id: uuid.UUID, data: JustificationIn
) -> RobReviewOut:
    """Soft-deletes an imported assessment so it can be imported again (justified)."""
    _require_admin(ctx)
    ensure_open(ctx, Stage.RISK_OF_BIAS)
    a = await _final(session, ctx, assessment_id)
    if a.kind != "imported":
        raise AppError("rob.discard_only_import", status_code=409)
    a.deleted_at = datetime.now(UTC)
    record(session, ctx, Stage.RISK_OF_BIAS, StageAction.REOPEN, data.justification.strip(), a.id)
    await session.commit()
    return await review(session, ctx)
