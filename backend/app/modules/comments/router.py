import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.modules.comments import service
from app.modules.projects.access import ProjectContext, member_access

router = APIRouter(prefix="/projects/{project_id}/comments", tags=["comments"])


@router.get("")
async def list_comments(
    entity: service.Entity,
    entity_id: uuid.UUID,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> list[service.CommentOut]:
    """Comments on one study, reference or analysis, oldest first."""
    return await service.list_comments(session, ctx, entity, entity_id)


@router.get("/members")
async def mentionable_members(
    ctx: ProjectContext = Depends(member_access), session: AsyncSession = Depends(get_session)
) -> list[service.MentionOut]:
    """Members that can be mentioned (names only)."""
    return await service.members(session, ctx)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_comment(
    body: service.CommentIn,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> service.CommentOut:
    return await service.create(session, ctx, body)


@router.put("/{comment_id}")
async def edit_comment(
    comment_id: uuid.UUID,
    body: service.CommentEdit,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> service.CommentOut:
    return await service.edit(session, ctx, comment_id, body)


@router.delete("/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_comment(
    comment_id: uuid.UUID,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> None:
    await service.delete(session, ctx, comment_id)
