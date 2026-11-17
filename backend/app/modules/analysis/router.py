from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.integrations.stats_client import StatsClient, get_stats_client
from app.modules.analysis import assembly
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
