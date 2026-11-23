"""Comments with mentions (docs/modulos.md 7.13; stage 6 step 3).

Every member may comment, readers included (an advisor reads and comments; comments
are not review data). Only the author edits a comment; the author or an admin removes
it (soft delete). Mentions must be members of the project.
"""

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ConflictError, ForbiddenError, NotFoundError
from app.modules.analysis.models import Analysis
from app.modules.auth.models import User
from app.modules.comments.models import Comment
from app.modules.notifications.service import notify
from app.modules.projects.access import ProjectContext
from app.modules.projects.models import ProjectMember
from app.modules.studies.models import Reference, Study

Entity = Literal["study", "reference", "analysis"]
MODELS: dict[str, Any] = {"study": Study, "reference": Reference, "analysis": Analysis}


class CommentIn(BaseModel):
    entity: Entity
    entity_id: uuid.UUID
    field: str | None = Field(default=None, max_length=120)
    text: str = Field(min_length=1, max_length=4000)
    mentions: list[uuid.UUID] = Field(default_factory=list, max_length=50)


class CommentEdit(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    mentions: list[uuid.UUID] = Field(default_factory=list, max_length=50)
    version: int


class MentionOut(BaseModel):
    user_id: uuid.UUID
    name: str


class CommentOut(BaseModel):
    id: uuid.UUID
    entity: str
    entity_id: uuid.UUID
    field: str | None
    text: str
    author_id: uuid.UUID | None
    author_name: str
    mentions: list[MentionOut]
    created_at: datetime
    edited: bool
    version: int


async def _members(session: AsyncSession, ctx: ProjectContext) -> dict[uuid.UUID, str]:
    rows = await session.execute(
        select(User.id, User.name)
        .join(ProjectMember, ProjectMember.user_id == User.id)
        .where(ProjectMember.project_id == ctx.project.id)
    )
    return {i: n for i, n in rows.all()}


async def members(session: AsyncSession, ctx: ProjectContext) -> list[MentionOut]:
    """Who can be mentioned (names only, never e-mails)."""
    found = await _members(session, ctx)
    return sorted((MentionOut(user_id=i, name=n) for i, n in found.items()), key=lambda m: m.name)


async def _check_target(
    session: AsyncSession, ctx: ProjectContext, entity: str, eid: uuid.UUID
) -> None:
    model = MODELS[entity]
    found = await session.scalar(
        select(model.id).where(model.id == eid, model.project_id == ctx.project.id)
    )
    if found is None:
        raise NotFoundError()


def _mentions(ids: list[uuid.UUID], names: dict[uuid.UUID, str]) -> list[str]:
    clean = list(dict.fromkeys(ids))
    if any(i not in names for i in clean):
        raise AppError("comments.mention_not_member", status_code=422)
    return [str(i) for i in clean]


def _out(c: Comment, names: dict[uuid.UUID, str]) -> CommentOut:
    return CommentOut(
        id=c.id,
        entity=c.entity,
        entity_id=c.entity_id,
        field=c.field,
        text=c.text,
        author_id=c.created_by,
        author_name=names.get(c.created_by, "") if c.created_by else "",
        mentions=[
            MentionOut(user_id=uuid.UUID(m), name=names.get(uuid.UUID(m), ""))
            for m in c.mentions or []
        ],
        created_at=c.created_at,
        edited=c.version > 1,
        version=c.version,
    )


async def _notify_mentions(
    session: AsyncSession, ctx: ProjectContext, c: Comment, before: set[str]
) -> None:
    new = {uuid.UUID(m) for m in c.mentions or [] if m not in before} - {ctx.user.id}
    await notify(
        session,
        new,
        ctx.project.id,
        "mention",
        f"mention:{c.id}",
        {
            "comment_id": str(c.id),
            "entity": c.entity,
            "entity_id": str(c.entity_id),
            "field": c.field,
            "author_name": ctx.user.name,
        },
    )


async def list_comments(
    session: AsyncSession, ctx: ProjectContext, entity: Entity, entity_id: uuid.UUID
) -> list[CommentOut]:
    await _check_target(session, ctx, entity, entity_id)
    names = await _members(session, ctx)
    rows = await session.scalars(
        select(Comment)
        .where(
            Comment.project_id == ctx.project.id,
            Comment.entity == entity,
            Comment.entity_id == entity_id,
        )
        .order_by(Comment.created_at)
    )
    return [_out(c, names) for c in rows]


async def create(session: AsyncSession, ctx: ProjectContext, data: CommentIn) -> CommentOut:
    await _check_target(session, ctx, data.entity, data.entity_id)
    text = data.text.strip()
    if not text:
        raise AppError("comments.empty", status_code=422)
    names = await _members(session, ctx)
    c = Comment(
        project_id=ctx.project.id,
        entity=data.entity,
        entity_id=data.entity_id,
        field=(data.field or "").strip() or None,
        text=text,
        mentions=_mentions(data.mentions, names),
        created_by=ctx.user.id,
    )
    session.add(c)
    await session.flush()
    await _notify_mentions(session, ctx, c, set())
    await session.commit()
    await session.refresh(c)
    return _out(c, names)


async def _get(session: AsyncSession, ctx: ProjectContext, comment_id: uuid.UUID) -> Comment:
    c = (
        await session.scalars(
            select(Comment).where(Comment.id == comment_id, Comment.project_id == ctx.project.id)
        )
    ).first()
    if c is None:
        raise NotFoundError()
    return c


async def edit(
    session: AsyncSession, ctx: ProjectContext, comment_id: uuid.UUID, data: CommentEdit
) -> CommentOut:
    c = await _get(session, ctx, comment_id)
    if c.created_by != ctx.user.id:
        raise ForbiddenError()
    if c.version != data.version:
        raise ConflictError()
    text = data.text.strip()
    if not text:
        raise AppError("comments.empty", status_code=422)
    names = await _members(session, ctx)
    before = set(c.mentions or [])
    c.text, c.mentions = text, _mentions(data.mentions, names)
    await _notify_mentions(session, ctx, c, before)
    await session.commit()
    await session.refresh(c)
    return _out(c, names)


async def delete(session: AsyncSession, ctx: ProjectContext, comment_id: uuid.UUID) -> None:
    c = await _get(session, ctx, comment_id)
    if c.created_by != ctx.user.id and not ctx.is_admin:
        raise ForbiddenError()
    c.deleted_at = datetime.now(UTC)
    await session.commit()
