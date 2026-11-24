from urllib.parse import quote

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.integrations.stats_client import StatsClient, get_stats_client
from app.modules.projects.access import ProjectContext, member_access
from app.modules.writing import service

router = APIRouter(prefix="/projects/{project_id}/writing", tags=["writing"])

FILE = {
    200: {
        "description": "The file.",
        "content": {"application/octet-stream": {"schema": {"type": "string", "format": "binary"}}},
    }
}


@router.get("/abstract")
async def get_abstract(
    ctx: ProjectContext = Depends(member_access), session: AsyncSession = Depends(get_session)
) -> service.AbstractOut:
    """The abstract the group is editing, with the congress limits."""
    return await service.get_abstract(session, ctx)


@router.put("/abstract")
async def save_abstract(
    body: service.AbstractIn,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> service.AbstractOut:
    return await service.save_abstract(session, ctx, body)


@router.post("/abstract/draft")
async def draft_abstract(
    body: service.DraftIn,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
    stats: StatsClient = Depends(get_stats_client),
) -> service.Sections:
    """Structured abstract with the system's numbers (no AI); the conclusion is left blank."""
    return await service.abstract_draft(session, ctx, stats, body)


@router.post("/methods-results.docx", response_class=Response, responses=FILE)  # type: ignore[arg-type]
async def methods_results(
    body: service.DraftIn,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
    stats: StatsClient = Depends(get_stats_client),
) -> Response:
    """Draft of Methods and Results as DOCX, with the system's numbers (no AI)."""
    content, name = await service.methods_results_docx(session, ctx, stats, body)
    disposition = f"attachment; filename=\"{name}\"; filename*=UTF-8''{quote(name)}"
    media = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return Response(content=content, media_type=media, headers={"Content-Disposition": disposition})
