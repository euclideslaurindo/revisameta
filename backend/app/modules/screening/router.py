import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.integrations.stats_client import StatsClient, get_stats_client
from app.modules.projects.access import ProjectContext, member_access
from app.modules.screening import service

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
) -> service.ScreeningQueuePage:
    """References to screen. While blinding is on, other reviewers' decisions are hidden."""
    return await service.queue(session, ctx, view, after, limit, q)


@router.get("/counts")
async def screening_counts(
    ctx: ProjectContext = Depends(member_access), session: AsyncSession = Depends(get_session)
) -> service.ScreeningCounts:
    return await service.counts(session, ctx)


@router.post("/references/{reference_id}/decision", status_code=status.HTTP_201_CREATED)
async def decide_reference(
    reference_id: uuid.UUID,
    body: service.ScreeningDecideIn,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> service.ScreeningDecisionOut:
    """Include, exclude or maybe (admin or reviewer). A new decision supersedes mine."""
    return await service.decide(session, ctx, reference_id, body)


@router.post("/undo")
async def undo_last_decision(
    ctx: ProjectContext = Depends(member_access), session: AsyncSession = Depends(get_session)
) -> service.ScreeningDecisionOut | None:
    """Withdraws my latest decision; the one before it (if any) comes back."""
    return await service.undo(session, ctx)


@router.get("/references/{reference_id}/history")
async def reference_history(
    reference_id: uuid.UUID,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> list[service.ScreeningDecisionOut]:
    return await service.history(session, ctx, reference_id)


@router.post("/references/{reference_id}/resolution")
async def resolve_conflict(
    reference_id: uuid.UUID,
    body: service.ScreeningResolveIn,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    """Final decision of a conflict, with the reason (admin)."""
    return await service.resolve(session, ctx, reference_id, body)


@router.delete("/references/{reference_id}/resolution", status_code=status.HTTP_204_NO_CONTENT)
async def reopen_conflict(
    reference_id: uuid.UUID,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> None:
    await service.reopen(session, ctx, reference_id)


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
    ctx: ProjectContext = Depends(member_access), session: AsyncSession = Depends(get_session)
) -> list[service.ScreeningAssignmentSummary]:
    return await service.assignments(session, ctx)


@router.post("/assignments")
async def assign_batch(
    body: service.ScreeningAssignIn,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> service.ScreeningAssignmentSummary:
    """Gives the next references to a reviewer (admin)."""
    return await service.assign(session, ctx, body)


@router.delete("/assignments/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def take_back_batch(
    user_id: uuid.UUID,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Takes back what the reviewer did not decide yet (admin)."""
    await service.unassign(session, ctx, user_id)


@router.get("/agreement")
async def screening_agreement(
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
    stats: StatsClient = Depends(get_stats_client),
) -> list[service.ScreeningAgreementOut]:
    """Cohen's kappa between reviewers (computed in R)."""
    return await service.agreement(session, ctx, stats)
