import uuid
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.session import get_session
from app.integrations.ai import AIProvider, get_ai_provider
from app.integrations.ai.base import AIUnavailableError
from app.integrations.stats_client import StatsClient, get_stats_client
from app.modules.ai import locate, metrics, settings, tutor
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


@router.post("/locate")
async def locate_passages(
    body: locate.LocateIn,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> locate.LocateOut:
    """Points at passages of a PDF that answer a question; every quote is checked against
    the PDF text and discarded when it is not there."""
    await settings.require(session, ctx, "locate")
    return await locate.locate(session, ctx, _provider(), body)


@router.get("/suggestions")
async def ai_suggestions(
    target_id: uuid.UUID,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> list[locate.SuggestionOut]:
    return await locate.suggestions(session, ctx, target_id)


@router.put("/suggestions/{suggestion_id}/decision")
async def decide_ai_suggestion(
    suggestion_id: uuid.UUID,
    body: locate.DecisionIn,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> locate.SuggestionOut:
    """A person marks the suggestion as useful (accepted) or not (rejected)."""
    return await locate.decide(session, ctx, suggestion_id, body)


@router.get("/metrics")
async def ai_metrics(
    ctx: ProjectContext = Depends(member_access), session: AsyncSession = Depends(get_session)
) -> metrics.MetricsOut:
    """Hit rate of each AI feature against the decisions of people in this project."""
    return await metrics.metrics(session, ctx)


FILE = {
    200: {
        "description": "The file.",
        "content": {"application/octet-stream": {"schema": {"type": "string", "format": "binary"}}},
    }
}


@router.get("/statement.docx", response_class=Response, responses=FILE)  # type: ignore[arg-type]
async def ai_statement(
    lang: Literal["pt-BR", "en"] = "pt-BR",
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """AI-use statement for the manuscript: features, provider, prompt versions, accuracy."""
    content, name = await metrics.statement(session, ctx, lang)
    disposition = f"attachment; filename=\"{name}\"; filename*=UTF-8''{quote(name)}"
    media = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return Response(content=content, media_type=media, headers={"Content-Disposition": disposition})
