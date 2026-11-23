"""In-app notifications (docs/modulos.md 7.13; stage 6 step 4).

- mention: someone mentioned you in a comment (on creation, and on edit for people
  newly mentioned). Never to the author.
- screening_conflict: the two screeners of a reference disagree; sent to the
  project admins, once per reference and stage.
- deadline: the project deadline is 7 days away or less; created when the user's
  notifications are read (no scheduler needed), once per deadline date.

A user sees only their own notifications, and only of projects they still belong to.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel
from sqlalchemy import any_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.modules.auth.models import User
from app.modules.notifications.models import Notification
from app.modules.projects.models import Project, ProjectMember, Role

DEADLINE_DAYS = 7
LIMIT = 50


class NotificationOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    project_title: str
    kind: str
    payload: dict[str, Any]
    created_at: datetime
    read: bool


class NotificationsOut(BaseModel):
    unread: int
    items: list[NotificationOut]


async def notify(
    session: AsyncSession,
    user_ids: set[uuid.UUID],
    project_id: uuid.UUID,
    kind: str,
    key: str,
    payload: dict[str, Any],
) -> None:
    """Adds one notification per user, skipping users who already have this key.
    The caller commits."""
    if not user_ids:
        return
    existing = set(
        await session.scalars(
            select(Notification.user_id).where(
                Notification.project_id == project_id,
                Notification.key == key,
                Notification.user_id.in_(user_ids),
            )
        )
    )
    for uid in user_ids - existing:
        session.add(
            Notification(user_id=uid, project_id=project_id, kind=kind, key=key, payload=payload)
        )


async def admins_of(session: AsyncSession, project_id: uuid.UUID) -> set[uuid.UUID]:
    rows = await session.scalars(
        select(ProjectMember.user_id).where(
            ProjectMember.project_id == project_id,
            any_(ProjectMember.roles) == Role.ADMIN.value,
        )
    )
    return set(rows)


async def _deadlines(session: AsyncSession, user: User) -> None:
    today = datetime.now(UTC).date()
    rows = await session.execute(
        select(Project.id, Project.deadline)
        .join(ProjectMember, ProjectMember.project_id == Project.id)
        .where(
            ProjectMember.user_id == user.id,
            Project.deadline.is_not(None),
            Project.deadline >= today,
            Project.deadline <= today + timedelta(days=DEADLINE_DAYS),
        )
    )
    added = False
    for pid, d in rows.all():
        if d is None:
            continue
        await notify(
            session,
            {user.id},
            pid,
            "deadline",
            f"deadline:{d.isoformat()}",
            {"deadline": d.isoformat(), "days": (d - today).days},
        )
        added = True
    if added:
        await session.commit()


async def mine(session: AsyncSession, user: User) -> NotificationsOut:
    await _deadlines(session, user)
    member_of = select(ProjectMember.project_id).where(ProjectMember.user_id == user.id)
    base = select(Notification, Project.title).join(Project, Project.id == Notification.project_id)
    rows = await session.execute(
        base.where(Notification.user_id == user.id, Notification.project_id.in_(member_of))
        .order_by(Notification.read_at.is_not(None), Notification.created_at.desc())
        .limit(LIMIT)
    )
    items = [
        NotificationOut(
            id=n.id,
            project_id=n.project_id,
            project_title=title,
            kind=n.kind,
            payload=n.payload,
            created_at=n.created_at,
            read=n.read_at is not None,
        )
        for n, title in rows.all()
    ]
    unread = await session.scalars(
        select(Notification.id).where(
            Notification.user_id == user.id,
            Notification.read_at.is_(None),
            Notification.project_id.in_(member_of),
        )
    )
    return NotificationsOut(unread=len(list(unread)), items=items)


async def mark_read(session: AsyncSession, user: User, notification_id: uuid.UUID) -> None:
    n = (
        await session.scalars(
            select(Notification).where(
                Notification.id == notification_id, Notification.user_id == user.id
            )
        )
    ).first()
    if n is None:
        raise NotFoundError()
    if n.read_at is None:
        n.read_at = datetime.now(UTC)
    await session.commit()


async def mark_all_read(session: AsyncSession, user: User) -> None:
    await session.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.read_at.is_(None))
        .values(read_at=datetime.now(UTC))
    )
    await session.commit()
