from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.modules.dashboard import service
from app.modules.projects.access import ProjectContext, member_access

router = APIRouter(prefix="/projects/{project_id}", tags=["dashboard"])


@router.get("/dashboard")
async def project_dashboard(
    ctx: ProjectContext = Depends(member_access), session: AsyncSession = Depends(get_session)
) -> service.DashboardOut:
    """Progress per stage, what is left for each person and the deadline countdown."""
    return await service.dashboard(session, ctx)
