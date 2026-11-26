"""The user's own data (LGPD, 10.2): export it and delete the account.

Deleting does not erase the work other people rely on. The account is anonymised
(name, e-mail, password and 2FA wiped; signed out everywhere), memberships end,
and projects where the person was alone are soft-deleted. Projects the person owns
together with others must be handed over first, so nobody loses a shared review.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.security import hash_password, new_opaque_token, verify_password
from app.modules.auth import two_factor
from app.modules.auth.models import EmailToken, RefreshToken, User
from app.modules.comments.models import Comment
from app.modules.projects.models import Project, ProjectMember, Role

DELETED_NAME = "Conta excluída"


class DeleteAccountIn(BaseModel):
    password: str = Field(min_length=1, max_length=256)
    otp_code: str | None = Field(default=None, max_length=20)


class BlockingProject(BaseModel):
    id: uuid.UUID
    title: str
    reason: str  # "owner_with_members" | "last_admin"


class DeletionCheckOut(BaseModel):
    """What happens if the account is deleted now."""

    blocking: list[BlockingProject]
    projects_deleted: list[str]  # titles of projects where the person is alone
    memberships_left: int


def _now() -> datetime:
    return datetime.now(UTC)


async def _memberships(
    session: AsyncSession, user_id: uuid.UUID
) -> list[tuple[ProjectMember, Project]]:
    rows = await session.execute(
        select(ProjectMember, Project)
        .join(Project, Project.id == ProjectMember.project_id)
        .where(
            ProjectMember.user_id == user_id,
            ProjectMember.deleted_at.is_(None),
            Project.deleted_at.is_(None),
        )
        .order_by(Project.title)
    )
    return [(m, p) for m, p in rows.all()]


async def _others(session: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID) -> list[Any]:
    rows = await session.scalars(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id != user_id,
            ProjectMember.deleted_at.is_(None),
        )
    )
    return list(rows)


async def deletion_check(session: AsyncSession, user: User) -> DeletionCheckOut:
    blocking: list[BlockingProject] = []
    alone: list[str] = []
    left = 0
    for member, project in await _memberships(session, user.id):
        others = await _others(session, project.id, user.id)
        if not others:
            alone.append(project.title)
        elif project.owner_id == user.id:
            blocking.append(
                BlockingProject(id=project.id, title=project.title, reason="owner_with_members")
            )
        elif Role.ADMIN in member.roles and not any(Role.ADMIN in o.roles for o in others):
            blocking.append(
                BlockingProject(id=project.id, title=project.title, reason="last_admin")
            )
        else:
            left += 1
    return DeletionCheckOut(blocking=blocking, projects_deleted=alone, memberships_left=left)


async def delete_account(session: AsyncSession, user: User, body: DeleteAccountIn) -> None:
    if not verify_password(user.password_hash, body.password):
        raise AppError("auth.wrong_password", status_code=400)
    if user.totp_enabled_at is not None and not (
        body.otp_code and two_factor.check(user, body.otp_code)
    ):
        raise AppError("auth.otp_invalid", status_code=400)
    check = await deletion_check(session, user)
    if check.blocking:
        raise AppError("account.transfer_first", status_code=409)

    now = _now()
    for member, project in await _memberships(session, user.id):
        if not await _others(session, project.id, user.id):
            project.deleted_at = now
        member.deleted_at = now

    random_secret, _ = new_opaque_token()
    user.name = DELETED_NAME
    user.email = f"deleted-{user.id}@invalid"
    user.password_hash = hash_password(random_secret)
    user.totp_secret = None
    user.totp_enabled_at = None
    user.recovery_codes = []
    user.is_active = False
    user.deleted_at = now
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    await session.execute(
        update(EmailToken)
        .where(EmailToken.user_id == user.id, EmailToken.used_at.is_(None))
        .values(used_at=now)
    )
    await session.commit()


async def export_data(session: AsyncSession, user: User) -> dict[str, Any]:
    """Everything personal the system keeps about the user, as JSON (portability)."""
    projects = [
        {"project_id": str(p.id), "title": p.title, "roles": list(m.roles), "since": m.created_at}
        for m, p in await _memberships(session, user.id)
    ]
    comments = await session.scalars(
        select(Comment)
        .where(Comment.created_by == user.id, Comment.deleted_at.is_(None))
        .order_by(Comment.created_at)
    )
    return {
        "exported_at": _now(),
        "account": {
            "id": str(user.id),
            "name": user.name,
            "email": user.email,
            "ui_language": user.ui_language,
            "created_at": user.created_at,
            "email_verified_at": user.email_verified_at,
            "terms_version": user.terms_version,
            "terms_accepted_at": user.terms_accepted_at,
            "two_factor": user.two_factor,
        },
        "projects": projects,
        "comments": [
            {
                "project_id": str(c.project_id),
                "entity": c.entity,
                "text": c.text,
                "created_at": c.created_at,
            }
            for c in comments
        ],
        "note": (
            "Project content is exported per project (backup ZIP on the project settings page)."
        ),
    }
