import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.integrations.stats_client import StatsClient, get_stats_client
from app.modules.projects.access import ProjectContext, member_access
from app.modules.references.service import SearchReferenceOut
from app.modules.screening import inclusion, reasons, service
from app.modules.studies.schemas import StudyOut

router = APIRouter(prefix="/projects/{project_id}/screening", tags=["screening"])


@router.get("/settings")
async def get_screening_settings(
    ctx: ProjectContext = Depends(member_access),
) -> service.ScreeningSettings:
    return service.settings_of(ctx)


@router.put("/settings")
async def put_screening_settings(
    body: service.ScreeningSettings,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> service.ScreeningSettings:
    """Keywords to highlight and blinding (admin)."""
    return await service.update_settings(session, ctx, body)


@router.get("/queue")
async def screening_queue(
    view: service.View = "todo",
    after: uuid.UUID | None = None,
    limit: int = Query(default=20, ge=1, le=200),
    q: str | None = Query(default=None, max_length=200),
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
    stage: service.Stage = "title_abstract",
) -> service.ScreeningQueuePage:
    """References to screen. While blinding is on, other reviewers' decisions are hidden."""
    return await service.queue(session, ctx, view, after, limit, q, stage=stage)


@router.get("/counts")
async def screening_counts(
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
    stage: service.Stage = "title_abstract",
) -> service.ScreeningCounts:
    return await service.counts(session, ctx, stage=stage)


@router.post("/references/{reference_id}/decision", status_code=status.HTTP_201_CREATED)
async def decide_reference(
    reference_id: uuid.UUID,
    body: service.ScreeningDecideIn,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
    stage: service.Stage = "title_abstract",
) -> service.ScreeningDecisionOut:
    """Include, exclude or maybe (admin or reviewer). A new decision supersedes mine."""
    return await service.decide(session, ctx, reference_id, body, stage=stage)


@router.post("/undo")
async def undo_last_decision(
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
    stage: service.Stage = "title_abstract",
) -> service.ScreeningDecisionOut | None:
    """Withdraws my latest decision; the one before it (if any) comes back."""
    return await service.undo(session, ctx, stage=stage)


@router.get("/references/{reference_id}/history")
async def reference_history(
    reference_id: uuid.UUID,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
    stage: service.Stage = "title_abstract",
) -> list[service.ScreeningDecisionOut]:
    return await service.history(session, ctx, reference_id, stage=stage)


@router.post("/references/{reference_id}/resolution")
async def resolve_conflict(
    reference_id: uuid.UUID,
    body: service.ScreeningResolveIn,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
    stage: service.Stage = "title_abstract",
) -> dict[str, str]:
    """Final decision of a conflict, with the reason (admin)."""
    return await service.resolve(session, ctx, reference_id, body, stage=stage)


@router.delete("/references/{reference_id}/resolution", status_code=status.HTTP_204_NO_CONTENT)
async def reopen_conflict(
    reference_id: uuid.UUID,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
    stage: service.Stage = "title_abstract",
) -> None:
    await service.reopen(session, ctx, reference_id, stage=stage)


@router.put("/references/{reference_id}/useful")
async def mark_useful(
    reference_id: uuid.UUID,
    body: service.ScreeningUsefulIn,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> dict[str, bool]:
    """Excluded but useful to cite in the Introduction or Discussion."""
    return await service.set_useful(session, ctx, reference_id, body)


@router.get("/assignments")
async def list_assignments(
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
    stage: service.Stage = "title_abstract",
) -> list[service.ScreeningAssignmentSummary]:
    return await service.assignments(session, ctx, stage=stage)


@router.post("/assignments")
async def assign_batch(
    body: service.ScreeningAssignIn,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
    stage: service.Stage = "title_abstract",
) -> service.ScreeningAssignmentSummary:
    """Gives the next references to a reviewer (admin)."""
    return await service.assign(session, ctx, body, stage=stage)


@router.delete("/assignments/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def take_back_batch(
    user_id: uuid.UUID,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
    stage: service.Stage = "title_abstract",
) -> None:
    """Takes back what the reviewer did not decide yet (admin)."""
    await service.unassign(session, ctx, user_id, stage=stage)


@router.get("/agreement")
async def screening_agreement(
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
    stats: StatsClient = Depends(get_stats_client),
    stage: service.Stage = "title_abstract",
) -> list[service.ScreeningAgreementOut]:
    """Cohen's kappa between reviewers (computed in R)."""
    return await service.agreement(session, ctx, stats, stage=stage)


# ---- Exclusion reasons (full text) ---------------------------------------------------


@router.get("/exclusion-reasons")
async def list_exclusion_reasons(
    ctx: ProjectContext = Depends(member_access), session: AsyncSession = Depends(get_session)
) -> list[reasons.ReasonOut]:
    """Reasons to exclude at full text, merged ones included (history)."""
    return await reasons.list_reasons(session, ctx)


@router.post("/exclusion-reasons", status_code=status.HTTP_201_CREATED)
async def create_exclusion_reason(
    body: reasons.ReasonIn,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> reasons.ReasonOut:
    return await reasons.create(session, ctx, body)


@router.patch("/exclusion-reasons/{reason_id}")
async def rename_exclusion_reason(
    reason_id: uuid.UUID,
    body: reasons.ReasonUpdate,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> reasons.ReasonOut:
    return await reasons.rename(session, ctx, reason_id, body)


@router.delete("/exclusion-reasons/{reason_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_exclusion_reason(
    reason_id: uuid.UUID,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Only a reason nobody used; used reasons are merged instead."""
    await reasons.remove(session, ctx, reason_id)


@router.post("/exclusion-reasons/{reason_id}/merge")
async def merge_exclusion_reason(
    reason_id: uuid.UUID,
    body: reasons.MergeIn,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> reasons.ReasonOut:
    """Moves every decision to another reason; this one stays listed as merged."""
    return await reasons.merge(session, ctx, reason_id, body)


# ---- Included articles become studies -----------------------------------------------


@router.get("/included")
async def included_waiting_for_study(
    ctx: ProjectContext = Depends(member_access), session: AsyncSession = Depends(get_session)
) -> list[SearchReferenceOut]:
    """Included at full text and not yet a study or a report of one."""
    return await inclusion.waiting(session, ctx)


@router.post("/included/{reference_id}/study", status_code=status.HTTP_201_CREATED)
async def included_to_study(
    reference_id: uuid.UUID,
    body: inclusion.ToStudyIn,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> StudyOut:
    """New study, or one more report of an existing study (same cohort). Admin."""
    return await inclusion.to_study(session, ctx, reference_id, body)
