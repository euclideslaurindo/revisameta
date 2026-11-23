"""Retention of inactive projects (docs/deploy.md 10.8; stage 6 step 6).

Approved rule: after 12 months without any change (last entry in the audit log, or the
creation date), the admins get a notice and the project is marked as archived. It is
only a mark: nothing is deleted, the project keeps working, and an admin unarchives it
with one click. Runs once a day in the worker.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenError
from app.modules.audit.models import AuditLog
from app.modules.notifications.service import admins_of, notify
from app.modules.projects.access import ProjectContext
from app.modules.projects.models import Project

INACTIVE_DAYS = 365


async def archive_inactive(session: AsyncSession, now: datetime | None = None) -> int:
    limit = (now or datetime.now(UTC)) - timedelta(days=INACTIVE_DAYS)
    last = (
        select(AuditLog.project_id, func.max(AuditLog.created_at).label("at"))
        .group_by(AuditLog.project_id)
        .subquery()
    )
    rows = await session.execute(
        select(Project, func.coalesce(last.c.at, Project.created_at))
        .outerjoin(last, last.c.project_id == Project.id)
        .where(
            Project.archived_at.is_(None),
            func.coalesce(last.c.at, Project.created_at) < limit,
        )
    )
    archived = 0
    for project, last_at in rows.all():
        project.archived_at = now or datetime.now(UTC)
        await notify(
            session,
            await admins_of(session, project.id),
            project.id,
            "archived",
            f"archived:{project.archived_at.date().isoformat()}",
            {"last_activity": last_at.date().isoformat()},
        )
        archived += 1
    await session.commit()
    return archived


async def unarchive(session: AsyncSession, ctx: ProjectContext) -> None:
    if not ctx.is_admin:
        raise ForbiddenError()
    ctx.project.archived_at = None
    await session.commit()
