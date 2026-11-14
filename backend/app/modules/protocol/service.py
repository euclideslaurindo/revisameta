import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ConflictError, NotFoundError
from app.modules.projects.access import ProjectContext
from app.modules.protocol.models import ComparisonGroup, Outcome
from app.modules.protocol.schemas import GroupCreate, GroupUpdate, OutcomeCreate, OutcomeUpdate


async def _get[Item: (Outcome, ComparisonGroup)](
    session: AsyncSession, model: type[Item], ctx: ProjectContext, item_id: uuid.UUID
) -> Item:
    item = (
        await session.scalars(
            select(model).where(model.id == item_id, model.project_id == ctx.project.id)
        )
    ).first()
    if item is None:
        raise NotFoundError()
    return item


async def _ensure_unique[Item: (Outcome, ComparisonGroup)](
    session: AsyncSession,
    model: type[Item],
    ctx: ProjectContext,
    column: str,
    value: str,
    exclude: uuid.UUID | None = None,
) -> None:
    col = getattr(model, column)
    query = select(func.count()).where(
        model.project_id == ctx.project.id, func.lower(col) == value.strip().lower()
    )
    if exclude is not None:
        query = query.where(model.id != exclude)
    if await session.scalar(query):
        raise AppError("protocol.duplicate_name", status_code=409)


async def list_outcomes(session: AsyncSession, ctx: ProjectContext) -> list[Outcome]:
    rows = await session.scalars(
        select(Outcome)
        .where(Outcome.project_id == ctx.project.id)
        .order_by(Outcome.position, Outcome.created_at)
    )
    return list(rows)


async def create_outcome(
    session: AsyncSession, ctx: ProjectContext, data: OutcomeCreate
) -> Outcome:
    await _ensure_unique(session, Outcome, ctx, "name", data.name)
    outcome = Outcome(
        project_id=ctx.project.id,
        created_by=ctx.user.id,
        **{**data.model_dump(), "name": data.name.strip(), "type": data.type.value},
    )
    session.add(outcome)
    await session.commit()
    return outcome


async def update_outcome(
    session: AsyncSession, ctx: ProjectContext, outcome_id: uuid.UUID, data: OutcomeUpdate
) -> Outcome:
    outcome = await _get(session, Outcome, ctx, outcome_id)
    if outcome.version != data.version:
        raise ConflictError()
    values = data.model_dump(exclude_unset=True, exclude={"version"})
    if "name" in values:
        await _ensure_unique(session, Outcome, ctx, "name", values["name"], exclude=outcome.id)
        values["name"] = values["name"].strip()
    if values.get("type") is not None:
        values["type"] = values["type"].value
    for key, value in values.items():
        setattr(outcome, key, value)
    await session.commit()
    return outcome


async def delete_outcome(session: AsyncSession, ctx: ProjectContext, outcome_id: uuid.UUID) -> None:
    outcome = await _get(session, Outcome, ctx, outcome_id)
    outcome.deleted_at = datetime.now(UTC)
    await session.commit()


async def list_groups(session: AsyncSession, ctx: ProjectContext) -> list[ComparisonGroup]:
    rows = await session.scalars(
        select(ComparisonGroup)
        .where(ComparisonGroup.project_id == ctx.project.id)
        .order_by(ComparisonGroup.position, ComparisonGroup.created_at)
    )
    return list(rows)


async def create_group(
    session: AsyncSession, ctx: ProjectContext, data: GroupCreate
) -> ComparisonGroup:
    await _ensure_unique(session, ComparisonGroup, ctx, "label", data.label)
    group = ComparisonGroup(
        project_id=ctx.project.id,
        created_by=ctx.user.id,
        **{**data.model_dump(), "label": data.label.strip()},
    )
    session.add(group)
    await session.commit()
    return group


async def update_group(
    session: AsyncSession, ctx: ProjectContext, group_id: uuid.UUID, data: GroupUpdate
) -> ComparisonGroup:
    group = await _get(session, ComparisonGroup, ctx, group_id)
    if group.version != data.version:
        raise ConflictError()
    values = data.model_dump(exclude_unset=True, exclude={"version"})
    if "label" in values:
        await _ensure_unique(session, ComparisonGroup, ctx, "label", values["label"], group.id)
        values["label"] = values["label"].strip()
    for key, value in values.items():
        setattr(group, key, value)
    await session.commit()
    return group


async def delete_group(session: AsyncSession, ctx: ProjectContext, group_id: uuid.UUID) -> None:
    group = await _get(session, ComparisonGroup, ctx, group_id)
    group.deleted_at = datetime.now(UTC)
    await session.commit()
