import uuid
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.integrations.stats_client import StatsClient, get_stats_client
from app.modules.grade import service, sof
from app.modules.projects.access import ProjectContext, member_access

router = APIRouter(prefix="/projects/{project_id}/grade", tags=["grade"])


@router.get("/settings")
async def grade_settings(ctx: ProjectContext = Depends(member_access)) -> service.GradeSettings:
    """Thresholds of the GRADE suggestions (approved defaults unless changed)."""
    return service.settings_of(ctx)


@router.put("/settings")
async def update_grade_settings(
    body: service.GradeSettings,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> service.GradeSettings:
    return await service.update_settings(session, ctx, body)


@router.post("/suggest")
async def suggest_grade(
    body: service.GradeBasis,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
    stats: StatsClient = Depends(get_stats_client),
) -> service.SuggestOut:
    """Runs the analysis of a result and suggests a change for each GRADE domain."""
    return await service.suggest(session, ctx, stats, body)


@router.get("")
async def grade_assessments(
    ctx: ProjectContext = Depends(member_access), session: AsyncSession = Depends(get_session)
) -> list[service.GradeOut]:
    return await service.assessments(session, ctx)


@router.put("")
async def save_grade(
    body: service.GradeIn,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
    stats: StatsClient = Depends(get_stats_client),
) -> service.GradeOut:
    """Saves the group's judgement of one result, with a justification for every change."""
    return await service.save(session, ctx, stats, body)


@router.delete("/{assessment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_grade(
    assessment_id: uuid.UUID,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> None:
    await service.delete(session, ctx, assessment_id)


FILE = {
    200: {
        "description": "The file.",
        "content": {"application/octet-stream": {"schema": {"type": "string", "format": "binary"}}},
    }
}


@router.get("/summary-of-findings", response_class=Response, responses=FILE)  # type: ignore[arg-type]
async def summary_of_findings(
    format: Literal["docx", "xlsx"] = "docx",
    lang: sof.Lang = "pt-BR",
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Summary of Findings table of the saved GRADE judgements, with justifications."""
    content, media, name = await sof.sof(session, ctx, format, lang)
    disposition = f"attachment; filename=\"{name}\"; filename*=UTF-8''{quote(name)}"
    return Response(content=content, media_type=media, headers={"Content-Disposition": disposition})
