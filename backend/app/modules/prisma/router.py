from urllib.parse import quote

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.integrations.stats_client import StatsClient, get_stats_client
from app.modules.prisma import checklist, service
from app.modules.projects.access import ProjectContext, member_access

router = APIRouter(prefix="/projects/{project_id}/prisma", tags=["prisma"])

FILE = {
    200: {
        "description": "The file.",
        "content": {"application/octet-stream": {"schema": {"type": "string", "format": "binary"}}},
    }
}


def _download(content: bytes, media: str, name: str) -> Response:
    disposition = f"attachment; filename=\"{name}\"; filename*=UTF-8''{quote(name)}"
    return Response(content=content, media_type=media, headers={"Content-Disposition": disposition})


@router.get("/counts")
async def prisma_counts(
    ctx: ProjectContext = Depends(member_access), session: AsyncSession = Depends(get_session)
) -> service.PrismaCounts:
    """Counts of the flow diagram, what was adjusted by hand and what does not add up."""
    return await service.counts(session, ctx)


@router.put("/adjustments/{key}")
async def adjust_prisma_count(
    key: service.Key,
    body: service.AdjustIn,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> service.PrismaCounts:
    """Types a count by hand, with a justification (admin). value=null removes it."""
    return await service.adjust(session, ctx, key, body)


@router.post("/flow", response_class=Response, responses=FILE)  # type: ignore[arg-type]
async def prisma_flow_diagram(
    body: service.FlowIn,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
    stats: StatsClient = Depends(get_stats_client),
) -> Response:
    """PRISMA 2020 flow diagram (SVG, or PNG at 300 dpi) in the chosen language."""
    return _download(*await service.flow(session, ctx, stats, body))


@router.get("/flow.docx", response_class=Response, responses=FILE)  # type: ignore[arg-type]
async def prisma_flow_docx(
    lang: service.Lang = "pt-BR",
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
    stats: StatsClient = Depends(get_stats_client),
) -> Response:
    content, name = await service.flow_docx(session, ctx, stats, lang)
    media = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return _download(content, media, name)


# ---- Checklist ---------------------------------------------------------------------------


@router.get("/checklist")
async def prisma_checklist(
    kind: checklist.Kind = "prisma2020",
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> checklist.ChecklistOut:
    """The 27 PRISMA 2020 items (42 rows), where each is reported, and which the system
    already has data for."""
    return await checklist.checklist(session, ctx, kind)


@router.put("/checklist/{code}")
async def record_checklist_item(
    code: str,
    body: checklist.ChecklistIn,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> checklist.ChecklistRow:
    """Status and location of one item in the manuscript."""
    return await checklist.record(session, ctx, code, body)


@router.get("/checklist.docx", response_class=Response, responses=FILE)  # type: ignore[arg-type]
async def prisma_checklist_docx(
    lang: checklist.Lang = "pt-BR",
    kind: checklist.Kind = "prisma2020",
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> Response:
    content, name = await checklist.docx(session, ctx, lang, kind)
    media = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return _download(content, media, name)
