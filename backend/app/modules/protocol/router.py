"""Protocol: members read; only project admins change it (docs/dominio.md, 6)."""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.modules.projects.access import ProjectContext, admin_access, member_access
from app.modules.protocol import service
from app.modules.protocol.schemas import (
    GroupCreate,
    GroupOut,
    GroupUpdate,
    OutcomeCreate,
    OutcomeOut,
    OutcomeUpdate,
)

router = APIRouter(prefix="/projects/{project_id}", tags=["protocol"])


@router.get("/outcomes")
async def list_outcomes(
    ctx: ProjectContext = Depends(member_access), session: AsyncSession = Depends(get_session)
) -> list[OutcomeOut]:
    return [OutcomeOut.model_validate(o) for o in await service.list_outcomes(session, ctx)]


@router.post("/outcomes", status_code=status.HTTP_201_CREATED)
async def create_outcome(
    body: OutcomeCreate,
    ctx: ProjectContext = Depends(admin_access),
    session: AsyncSession = Depends(get_session),
) -> OutcomeOut:
    return OutcomeOut.model_validate(await service.create_outcome(session, ctx, body))


@router.patch("/outcomes/{outcome_id}")
async def update_outcome(
    outcome_id: uuid.UUID,
    body: OutcomeUpdate,
    ctx: ProjectContext = Depends(admin_access),
    session: AsyncSession = Depends(get_session),
) -> OutcomeOut:
    return OutcomeOut.model_validate(await service.update_outcome(session, ctx, outcome_id, body))


@router.delete("/outcomes/{outcome_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_outcome(
    outcome_id: uuid.UUID,
    ctx: ProjectContext = Depends(admin_access),
    session: AsyncSession = Depends(get_session),
) -> None:
    await service.delete_outcome(session, ctx, outcome_id)


@router.get("/comparison-groups")
async def list_groups(
    ctx: ProjectContext = Depends(member_access), session: AsyncSession = Depends(get_session)
) -> list[GroupOut]:
    return [GroupOut.model_validate(g) for g in await service.list_groups(session, ctx)]


@router.post("/comparison-groups", status_code=status.HTTP_201_CREATED)
async def create_group(
    body: GroupCreate,
    ctx: ProjectContext = Depends(admin_access),
    session: AsyncSession = Depends(get_session),
) -> GroupOut:
    return GroupOut.model_validate(await service.create_group(session, ctx, body))


@router.patch("/comparison-groups/{group_id}")
async def update_group(
    group_id: uuid.UUID,
    body: GroupUpdate,
    ctx: ProjectContext = Depends(admin_access),
    session: AsyncSession = Depends(get_session),
) -> GroupOut:
    return GroupOut.model_validate(await service.update_group(session, ctx, group_id, body))


@router.delete("/comparison-groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(
    group_id: uuid.UUID,
    ctx: ProjectContext = Depends(admin_access),
    session: AsyncSession = Depends(get_session),
) -> None:
    await service.delete_group(session, ctx, group_id)
