from urllib.parse import quote

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.integrations.stats_client import StatsClient, get_stats_client
from app.modules.analysis import assembly, run
from app.modules.projects.access import ProjectContext, member_access

router = APIRouter(prefix="/projects/{project_id}/analyses", tags=["analysis"])


@router.post("/preview")
async def preview_analysis(
    body: assembly.AssemblyIn,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
    stats: StatsClient = Depends(get_stats_client),
) -> assembly.AssemblyOut:
    """Which studies enter the analysis, with which numbers, and why the others do not.

    Every number is computed by the R service; nothing is saved.
    """
    return await assembly.assemble(session, ctx, stats, body)


@router.post("/run")
async def run_analysis(
    body: run.RunIn,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
    stats: StatsClient = Depends(get_stats_client),
) -> run.RunOut:
    """Runs the model in the R service. Refused while the assembly has a block."""
    return await run.run(session, ctx, stats, body)


FILE_RESPONSE = {
    200: {
        "description": "The figure.",
        "content": {"application/octet-stream": {"schema": {"type": "string", "format": "binary"}}},
    }
}


@router.post("/forest-plot", response_class=Response, responses=FILE_RESPONSE)  # type: ignore[arg-type]
async def analysis_forest_plot(
    body: run.ForestIn,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
    stats: StatsClient = Depends(get_stats_client),
) -> Response:
    """Forest plot (SVG, or PNG at 300 dpi) in the chosen output language."""
    content, media, name = await run.forest_plot(session, ctx, stats, body)
    disposition = f"attachment; filename=\"{name}\"; filename*=UTF-8''{quote(name)}"
    return Response(content=content, media_type=media, headers={"Content-Disposition": disposition})
