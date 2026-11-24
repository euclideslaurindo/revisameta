from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.modules.ai import settings
from app.modules.projects.access import ProjectContext, member_access

router = APIRouter(prefix="/projects/{project_id}/ai", tags=["ai"])


@router.get("/settings")
async def ai_settings(
    ctx: ProjectContext = Depends(member_access), session: AsyncSession = Depends(get_session)
) -> settings.AISettingsOut:
    """Whether the AI is on in this project, the data-use notice and who accepted it."""
    return await settings.get(session, ctx)


@router.put("/settings")
async def update_ai_settings(
    body: settings.AISettingsIn,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> settings.AISettingsOut:
    """Turns the AI on (admin, accepting the current notice) or off."""
    return await settings.update(session, ctx, body)
