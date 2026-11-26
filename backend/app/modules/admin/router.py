"""System administration (docs/dominio.md, 6): users, quotas and service status.

System admins manage accounts and limits; they do NOT see project content unless
they are members of the project like anyone else.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.core.errors import AppError, NotFoundError
from app.db.session import get_session
from app.modules.auth.models import RefreshToken, User
from app.modules.projects.models import Project
from app.modules.quotas import service as quotas
from app.modules.quotas.router import require_system_admin
from app.modules.quotas.service import QuotaKind

router = APIRouter(prefix="/admin", tags=["admin"])

PAGE = 50


class AdminUserOut(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    is_active: bool
    is_system_admin: bool
    email_verified: bool
    two_factor: bool
    created_at: datetime
    projects_owned: int


class AdminUserPage(BaseModel):
    items: list[AdminUserOut]
    total: int
    offset: int
    limit: int


class AdminUserUpdate(BaseModel):
    is_active: bool | None = None
    is_system_admin: bool | None = None


class AdminOverview(BaseModel):
    users: int
    users_verified: int
    users_inactive: int
    projects: int
    default_quotas: dict[str, int]


@router.get("/overview")
async def overview(
    _admin: User = Depends(require_system_admin), session: AsyncSession = Depends(get_session)
) -> AdminOverview:
    alive = User.deleted_at.is_(None)
    users = await session.scalar(select(func.count()).select_from(User).where(alive))
    verified = await session.scalar(
        select(func.count()).select_from(User).where(alive, User.email_verified_at.is_not(None))
    )
    inactive = await session.scalar(
        select(func.count()).select_from(User).where(alive, User.is_active.is_(False))
    )
    projects = await session.scalar(
        select(func.count()).select_from(Project).where(Project.deleted_at.is_(None))
    )
    return AdminOverview(
        users=int(users or 0),
        users_verified=int(verified or 0),
        users_inactive=int(inactive or 0),
        projects=int(projects or 0),
        default_quotas={k.value: quotas.default_limit(k) for k in QuotaKind},
    )


@router.get("/users")
async def list_users(
    q: str | None = Query(default=None, max_length=200),
    offset: int = Query(default=0, ge=0),
    _admin: User = Depends(require_system_admin),
    session: AsyncSession = Depends(get_session),
) -> AdminUserPage:
    """Accounts (deleted ones left out), newest first, searchable by name or e-mail."""
    where: list[ColumnElement[bool]] = [User.deleted_at.is_(None)]
    if q and q.strip():
        like = f"%{q.strip().lower()}%"
        where.append(or_(func.lower(User.name).like(like), func.lower(User.email).like(like)))
    total = await session.scalar(select(func.count()).select_from(User).where(*where))
    owned = (
        select(Project.owner_id, func.count().label("n"))
        .where(Project.deleted_at.is_(None))
        .group_by(Project.owner_id)
        .subquery()
    )
    rows = await session.execute(
        select(User, func.coalesce(owned.c.n, 0))
        .outerjoin(owned, owned.c.owner_id == User.id)
        .where(*where)
        .order_by(User.created_at.desc())
        .offset(offset)
        .limit(PAGE)
    )
    items = [
        AdminUserOut(
            id=u.id,
            name=u.name,
            email=u.email,
            is_active=u.is_active,
            is_system_admin=u.is_system_admin,
            email_verified=u.email_verified_at is not None,
            two_factor=u.two_factor,
            created_at=u.created_at,
            projects_owned=int(n),
        )
        for u, n in rows.all()
    ]
    return AdminUserPage(items=items, total=int(total or 0), offset=offset, limit=PAGE)


@router.patch("/users/{user_id}")
async def update_user(
    user_id: uuid.UUID,
    body: AdminUserUpdate,
    admin: User = Depends(require_system_admin),
    session: AsyncSession = Depends(get_session),
) -> AdminUserOut:
    """Suspend/reactivate an account or grant/remove system administration."""
    user = await session.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise NotFoundError()
    if user.id == admin.id and (body.is_active is False or body.is_system_admin is False):
        # Avoids locking the last administrator out by mistake.
        raise AppError("admin.not_on_self", status_code=409)
    if body.is_system_admin is not None:
        user.is_system_admin = body.is_system_admin
    if body.is_active is not None:
        user.is_active = body.is_active
        if not body.is_active:
            await session.execute(
                update(RefreshToken)
                .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
                .values(revoked_at=datetime.now(UTC))
            )
    await session.commit()
    owned = await quotas.projects_used(session, user.id)
    return AdminUserOut(
        id=user.id,
        name=user.name,
        email=user.email,
        is_active=user.is_active,
        is_system_admin=user.is_system_admin,
        email_verified=user.email_verified_at is not None,
        two_factor=user.two_factor,
        created_at=user.created_at,
        projects_owned=owned,
    )
