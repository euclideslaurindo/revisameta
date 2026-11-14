import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.modules.projects.access import ProjectContext, admin_access, member_access
from app.modules.risk_of_bias import tools

router = APIRouter(prefix="/projects/{project_id}/rob", tags=["risk_of_bias"])


@router.get("/catalog")
async def rob_catalog(ctx: ProjectContext = Depends(member_access)) -> list[tools.CatalogItem]:
    """Instruments available (structure only; official wording is pasted by the admin)."""
    return tools.catalog_items()


@router.get("/tools")
async def list_rob_tools(
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> list[tools.ToolOut]:
    return [tools.tool_out(t) for t in await tools.project_tools(session, ctx)]


@router.post("/tools", status_code=status.HTTP_201_CREATED)
async def enable_rob_tool(
    body: tools.EnableIn,
    ctx: ProjectContext = Depends(admin_access),
    session: AsyncSession = Depends(get_session),
) -> tools.ToolOut:
    """Enables an instrument in the project (a copy that keeps its version)."""
    return await tools.enable(session, ctx, body)


@router.put("/tools/{tool_id}/texts")
async def set_rob_tool_texts(
    tool_id: uuid.UUID,
    body: tools.TextsIn,
    ctx: ProjectContext = Depends(admin_access),
    session: AsyncSession = Depends(get_session),
) -> tools.ToolOut:
    """Official wording of the questions, pasted from the official source."""
    return await tools.set_texts(session, ctx, tool_id, body)


@router.put("/tools/{tool_id}/structure")
async def set_rob_tool_structure(
    tool_id: uuid.UUID,
    body: tools.GenericStructureIn,
    ctx: ProjectContext = Depends(admin_access),
    session: AsyncSession = Depends(get_session),
) -> tools.ToolOut:
    """Domains of the generic instrument, defined by the group."""
    return await tools.set_generic_structure(session, ctx, tool_id, body)


@router.get("/studies/{study_id}/tool")
async def get_study_rob_tool(
    study_id: uuid.UUID,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> tools.StudyToolOut:
    """Instrument suggested by the study design and the one confirmed by the admin."""
    return await tools.study_tool(session, ctx, study_id)


@router.put("/studies/{study_id}/tool")
async def confirm_study_rob_tool(
    study_id: uuid.UUID,
    body: tools.StudyToolIn,
    ctx: ProjectContext = Depends(admin_access),
    session: AsyncSession = Depends(get_session),
) -> tools.StudyToolOut:
    return await tools.confirm_study_tool(session, ctx, study_id, body)
