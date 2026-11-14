"""Final review before locking the extraction (block F, docs/modulos.md 7.5.1, item 17).

For every number that analyses will use (the consensus of each study) the review
shows its value, type, origin in the article, who extracted it, how it was checked
and the alerts still open. The stage locks only when every study has a submitted
consensus and no open alert; unlocking or reopening a consensus needs a
justification, recorded in the stage history.
"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ForbiddenError
from app.modules.auth.models import User
from app.modules.extraction.alerts import AlertOut, sync_alerts
from app.modules.extraction.comparison import (
    ROW_NUMBERS,
    SEP,
    Comparison,
    arm_key,
    compare,
    number_text,
)
from app.modules.extraction.consensus import _decisions, _extractions, _form, snapshot
from app.modules.extraction.models import (
    AlertStatus,
    Extraction,
    ExtractionDecision,
    ExtractionStatus,
)
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
from app.modules.protocol.models import ComparisonGroup, Outcome
from app.modules.studies.models import Study

# ---- Schemas -------------------------------------------------------------------------


class NumberCheck(BaseModel):
    """How one number of the consensus was checked.

    status: empty (no value: nothing to check) | agreed (both extractors typed it) |
    decided (divergence settled) | undecided | edited (changed in the consensus
    without a decision) |
    one_extractor (only one extractor recorded the row) | single (no double
    extraction: checked when the admin submitted the consensus).
    """

    status: str
    choice: str | None = None
    by: str | None = None


class ReviewNumber(BaseModel):
    field: str
    value: str
    check: NumberCheck


class ReviewRow(BaseModel):
    outcome_name: str
    timepoint: str
    arm_label: str
    group_label: str | None
    value_type: str
    dispersion_type: str | None
    dispersion_source: str | None
    source_location: str | None
    has_annotation: bool
    numbers: list[ReviewNumber]


class ReviewArm(BaseModel):
    arm_label: str
    group_label: str | None
    n: int | None
    check: NumberCheck


class ReviewStudy(BaseModel):
    study_id: uuid.UUID
    label: str
    consensus_id: uuid.UUID | None
    consensus_status: str | None
    extractors: list[str]
    checked_by: str | None
    checked_at: datetime | None
    open_alerts: list[AlertOut]
    justified_alerts: int
    arms: list[ReviewArm]
    rows: list[ReviewRow]
    blockers: list[str]


class FinalReviewOut(BaseModel):
    locked: bool
    can_lock: bool
    total: int
    ready: int
    studies: list[ReviewStudy]
    history: list[StageEventOut]


class JustificationIn(BaseModel):
    justification: str = Field(min_length=5, max_length=1000)


# ---- Review --------------------------------------------------------------------------


async def _names(session: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    ids = {i for i in ids if i is not None}
    if not ids:
        return {}
    return {u.id: u.name for u in await session.scalars(select(User).where(User.id.in_(ids)))}


def _check(
    key: str,
    consensus_value: Any,
    comparison: Comparison | None,
    decisions: dict[str, ExtractionDecision],
    names: dict[uuid.UUID, str],
    checker: str | None,
    row_present_key: str | None = None,
) -> NumberCheck:
    if consensus_value is None:
        return NumberCheck(status="empty")
    if comparison is None:
        return NumberCheck(status="single", by=checker)
    items = {i.key: i for i in comparison.items}
    item = items.get(key)
    if item is None:
        # The row (or arm) exists for one extractor only: its presence was decided.
        present = items.get(row_present_key or "")
        decision = decisions.get(row_present_key or "")
        if present is not None and decision is not None:
            return NumberCheck(
                status="one_extractor", choice=decision.choice, by=names.get(decision.decided_by)
            )
        return NumberCheck(status="edited")
    if not item.divergent:
        same = consensus_value == item.value_a
        return NumberCheck(status="agreed" if same else "edited")
    decision = decisions.get(key)
    if decision is None:
        return NumberCheck(status="undecided")
    chosen = {"a": item.value_a, "b": item.value_b}.get(decision.choice)
    if decision.choice in ("a", "b") and consensus_value != chosen:
        return NumberCheck(status="edited")
    return NumberCheck(status="decided", choice=decision.choice, by=names.get(decision.decided_by))


async def _study_review(
    session: AsyncSession,
    ctx: ProjectContext,
    study: Study,
    outcomes: dict[str, str],
    groups: dict[str, str],
) -> ReviewStudy:
    individuals, consensus = await _extractions(session, ctx, study.id)
    all_individuals = list(
        await session.scalars(
            select(Extraction).where(
                Extraction.study_id == study.id,
                Extraction.project_id == ctx.project.id,
                Extraction.extractor_id.is_not(None),
            )
        )
    )
    names = await _names(
        session,
        {e.extractor_id for e in all_individuals if e.extractor_id}
        | ({consensus.submitted_by} if consensus and consensus.submitted_by else set()),
    )
    out = ReviewStudy(
        study_id=study.id,
        label=study.label,
        consensus_id=consensus.id if consensus else None,
        consensus_status=consensus.status if consensus else None,
        extractors=[names[e.extractor_id] for e in all_individuals if e.extractor_id in names],
        checked_by=names.get(consensus.submitted_by)
        if consensus and consensus.submitted_by
        else None,
        checked_at=consensus.submitted_at if consensus else None,
        open_alerts=[],
        justified_alerts=0,
        arms=[],
        rows=[],
        blockers=[],
    )
    if consensus is None:
        out.blockers.append("review.no_consensus")
        return out
    if consensus.status == ExtractionStatus.DRAFT:
        out.blockers.append("review.consensus_draft")

    active = await sync_alerts(session, ctx, consensus)
    out.open_alerts = [AlertOut.model_validate(a) for a in active if a.status == AlertStatus.OPEN]
    out.justified_alerts = len([a for a in active if a.status == AlertStatus.JUSTIFIED])
    if out.open_alerts:
        out.blockers.append("review.open_alerts")

    comparison: Comparison | None = None
    decisions: dict[str, ExtractionDecision] = {}
    if ctx.project.double_extraction and len(individuals) >= 2:
        form = await _form(session, ctx)
        a, b = await snapshot(session, individuals[0]), await snapshot(session, individuals[1])
        comparison = compare(a, b, form)
        decisions = await _decisions(session, consensus)
    names |= await _names(session, {d.decided_by for d in decisions.values()})
    checker = out.checked_by

    cons = await snapshot(session, consensus)
    arms = {str(arm.id): arm for arm in cons.arms}
    for arm in sorted(cons.arms, key=lambda x: (x.position, x.created_at)):
        akey = arm_key(arm)
        out.arms.append(
            ReviewArm(
                arm_label=arm.label,
                group_label=groups.get(str(arm.mapped_group_id)),
                n=arm.n,
                check=_check(
                    SEP.join(("arm", akey, "n")),
                    arm.n,
                    comparison,
                    decisions,
                    names,
                    checker,
                    SEP.join(("arm", akey, "present")),
                ),
            )
        )
    for row in cons.rows:
        row_arm = arms.get(str(row.arm_id))
        if row_arm is None:
            continue
        akey = arm_key(row_arm)

        def key(field: str, akey: str = akey, row: Any = row) -> str:
            return SEP.join(("row", str(row.outcome_id), akey, field, row.timepoint))

        numbers = []
        for field in ROW_NUMBERS:
            value = number_text(getattr(row, field))
            if value is None:
                continue
            numbers.append(
                ReviewNumber(
                    field=field,
                    value=value,
                    check=_check(
                        key(field), value, comparison, decisions, names, checker, key("present")
                    ),
                )
            )
        out.rows.append(
            ReviewRow(
                outcome_name=outcomes.get(str(row.outcome_id), ""),
                timepoint=row.timepoint,
                arm_label=row_arm.label,
                group_label=groups.get(str(row_arm.mapped_group_id)),
                value_type=row.value_type,
                dispersion_type=row.dispersion_type,
                dispersion_source=row.dispersion_source,
                source_location=row.source_location,
                has_annotation=row.annotation_id is not None,
                numbers=numbers,
            )
        )
    return out


async def final_review(session: AsyncSession, ctx: ProjectContext) -> FinalReviewOut:
    studies = list(
        await session.scalars(
            select(Study).where(Study.project_id == ctx.project.id).order_by(Study.label)
        )
    )
    outcomes = {
        str(o.id): o.name
        for o in await session.scalars(select(Outcome).where(Outcome.project_id == ctx.project.id))
    }
    groups = {
        str(g.id): g.label
        for g in await session.scalars(
            select(ComparisonGroup).where(ComparisonGroup.project_id == ctx.project.id)
        )
    }
    reviews = [await _study_review(session, ctx, s, outcomes, groups) for s in studies]
    await session.commit()  # alerts were brought up to date
    ready = len([r for r in reviews if not r.blockers])
    return FinalReviewOut(
        locked=is_locked(ctx, Stage.EXTRACTION),
        can_lock=bool(reviews) and ready == len(reviews),
        total=len(reviews),
        ready=ready,
        studies=reviews,
        history=await events(session, ctx, Stage.EXTRACTION),
    )


# ---- Lock, unlock, reopen ------------------------------------------------------------


def _require_admin(ctx: ProjectContext) -> None:
    if not ctx.is_admin:
        raise ForbiddenError()


async def _consensuses(session: AsyncSession, ctx: ProjectContext) -> list[Extraction]:
    return list(
        await session.scalars(
            select(Extraction).where(
                Extraction.project_id == ctx.project.id,
                Extraction.kind == "consensus",
            )
        )
    )


async def lock(session: AsyncSession, ctx: ProjectContext) -> FinalReviewOut:
    _require_admin(ctx)
    ensure_open(ctx, Stage.EXTRACTION)
    review = await final_review(session, ctx)
    if not review.can_lock:
        raise AppError("review.not_ready", status_code=409, ready=review.ready, total=review.total)
    for consensus in await _consensuses(session, ctx):
        if consensus.status == ExtractionStatus.SUBMITTED:
            consensus.status = ExtractionStatus.LOCKED
    set_locked(ctx, Stage.EXTRACTION, True)
    record(session, ctx, Stage.EXTRACTION, StageAction.LOCK)
    await session.commit()
    return await final_review(session, ctx)


async def unlock(
    session: AsyncSession, ctx: ProjectContext, data: JustificationIn
) -> FinalReviewOut:
    _require_admin(ctx)
    if not is_locked(ctx, Stage.EXTRACTION):
        raise AppError("stage.not_locked", status_code=409)
    for consensus in await _consensuses(session, ctx):
        if consensus.status == ExtractionStatus.LOCKED:
            consensus.status = ExtractionStatus.SUBMITTED
    set_locked(ctx, Stage.EXTRACTION, False)
    record(session, ctx, Stage.EXTRACTION, StageAction.UNLOCK, data.justification.strip())
    await session.commit()
    return await final_review(session, ctx)


async def reopen(
    session: AsyncSession, ctx: ProjectContext, extraction_id: uuid.UUID, data: JustificationIn
) -> None:
    """Puts a submitted consensus back to draft to correct a number (justified)."""
    _require_admin(ctx)
    ensure_open(ctx, Stage.EXTRACTION)
    consensus = (
        await session.scalars(
            select(Extraction).where(
                Extraction.id == extraction_id,
                Extraction.project_id == ctx.project.id,
                Extraction.kind == "consensus",
            )
        )
    ).first()
    if consensus is None:
        raise AppError("review.not_a_consensus", status_code=404)
    if consensus.status != ExtractionStatus.SUBMITTED:
        raise AppError("review.not_submitted", status_code=409)
    consensus.status = ExtractionStatus.DRAFT
    consensus.submitted_by = None
    consensus.submitted_at = None
    record(
        session,
        ctx,
        Stage.EXTRACTION,
        StageAction.REOPEN,
        data.justification.strip(),
        target_id=consensus.id,
    )
    await session.commit()
