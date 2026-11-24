from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.session import get_session
from app.integrations.ai import AIProvider, get_ai_provider
from app.integrations.ai.base import AIUnavailableError
from app.integrations.stats_client import StatsClient, get_stats_client
from app.modules.ai import settings, tutor
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


def _provider() -> AIProvider:
    try:
        return get_ai_provider()
    except AIUnavailableError as error:
        raise AppError("ai.unavailable", status_code=503) from error


@router.post("/tutor")
async def ask_tutor(
    body: tutor.TutorIn,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
    stats: StatsClient = Depends(get_stats_client),
) -> tutor.TutorOut:
    """Explains a concept or an analysis of the project. Numbers come from R; any number
    the AI writes by itself is returned in `unverified`."""
    await settings.require(session, ctx, "tutor")
    return await tutor.ask(session, ctx, stats, _provider(), body)
