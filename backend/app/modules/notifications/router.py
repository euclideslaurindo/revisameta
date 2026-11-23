import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.notifications import service

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("")
async def my_notifications(
    user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)
) -> service.NotificationsOut:
    """My notifications (unread first) and how many are unread."""
    return await service.mine(session, user)


@router.post("/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def read_notification(
    notification_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    await service.mark_read(session, user, notification_id)


@router.post("/read-all", status_code=status.HTTP_204_NO_CONTENT)
async def read_all_notifications(
    user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)
) -> None:
    await service.mark_all_read(session, user)
