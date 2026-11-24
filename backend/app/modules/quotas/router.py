import uuid

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenError, NotFoundError
from app.db.session import get_session
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.quotas import service
from app.modules.quotas.service import QuotaKind

router = APIRouter(tags=["quotas"])


class UsageItem(BaseModel):
    used: float
    limit: float


class UsageOut(BaseModel):
    projects: UsageItem
    storage_mb: UsageItem
    ai_calls: UsageItem  # today (UTC)


class QuotaUpdate(BaseModel):
    kind: QuotaKind
    limit: int | None = Field(default=None, ge=0)  # null = back to default


def require_system_admin(user: User = Depends(get_current_user)) -> User:
    """System admins manage quotas and users; they do NOT see project content."""
    if not user.is_system_admin:
        raise ForbiddenError()
    return user


@router.get("/me/usage")
async def my_usage(
    user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)
) -> UsageOut:
    return UsageOut.model_validate(await service.usage(session, user.id))


@router.get("/admin/users/{user_id}/usage")
async def user_usage(
    user_id: uuid.UUID,
    _admin: User = Depends(require_system_admin),
    session: AsyncSession = Depends(get_session),
) -> UsageOut:
    if await session.get(User, user_id) is None:
        raise NotFoundError()
    return UsageOut.model_validate(await service.usage(session, user_id))


@router.put("/admin/users/{user_id}/quotas", status_code=status.HTTP_204_NO_CONTENT)
async def set_quota(
    user_id: uuid.UUID,
    body: QuotaUpdate,
    _admin: User = Depends(require_system_admin),
    session: AsyncSession = Depends(get_session),
) -> None:
    if await session.get(User, user_id) is None:
        raise NotFoundError()
    await service.set_limit(session, user_id, body.kind, body.limit)
