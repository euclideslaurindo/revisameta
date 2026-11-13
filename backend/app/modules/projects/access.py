"""Project isolation: every project route goes through `project_access` (CLAUDE.md 0.1, rule 10).

- Non-members get 404 (the project's existence is not revealed), including system admins.
- Members without the required role get 403.
- Admins can do everything inside their project.
"""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenError, NotFoundError
from app.db.session import get_session
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.projects.models import Project, ProjectMember, Role


@dataclass
class ProjectContext:
    project: Project
    member: ProjectMember
    user: User

    @property
    def roles(self) -> set[Role]:
        return {Role(r) for r in self.member.roles}

    @property
    def is_admin(self) -> bool:
        return Role.ADMIN in self.roles


async def load_membership(
    session: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID
) -> tuple[Project, ProjectMember] | None:
    row = (
        await session.execute(
            select(Project, ProjectMember)
            .join(ProjectMember, ProjectMember.project_id == Project.id)
            .where(Project.id == project_id, ProjectMember.user_id == user_id)
        )
    ).first()
    return (row[0], row[1]) if row else None


def project_access(*allowed: Role) -> Callable[..., Awaitable[ProjectContext]]:
    """Dependency factory. With no roles, any member may access (read)."""

    async def dependency(
        project_id: uuid.UUID,
        user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> ProjectContext:
        found = await load_membership(session, project_id, user.id)
        if found is None:
            raise NotFoundError()
        context = ProjectContext(project=found[0], member=found[1], user=user)
        if allowed and not context.is_admin and not (context.roles & set(allowed)):
            raise ForbiddenError()
        return context

    return dependency


member_access = project_access()
admin_access = project_access(Role.ADMIN)
