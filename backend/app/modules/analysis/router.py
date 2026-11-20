import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.integrations.stats_client import StatsClient, get_stats_client
from app.modules.analysis import (
    assembly,
    history,
    publication_bias,
    run,
    sensitivity,
    subgroups,
)
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


@router.post("/sensitivity")
async def sensitivity_analysis(
    body: sensitivity.SensitivityIn,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
    stats: StatsClient = Depends(get_stats_client),
) -> sensitivity.SensitivityOut:
    """Reruns the analysis changing one thing (leave one out, risk of bias, model...)."""
    return await sensitivity.sensitivity(session, ctx, stats, body)


@router.post("/subgroups")
async def subgroup_analysis(
    body: subgroups.SubgroupIn,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
    stats: StatsClient = Depends(get_stats_client),
) -> subgroups.SubgroupOut:
    """One model per subgroup (form field, risk of bias or cut-off) and the test of differences."""
    return await subgroups.subgroups(session, ctx, stats, body)


@router.post("/egger")
async def egger_test(
    body: run.RunIn,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
    stats: StatsClient = Depends(get_stats_client),
) -> publication_bias.EggerOut:
    """Egger's test for small-study effects; says when there are fewer than 10 studies."""
    return await publication_bias.egger(session, ctx, stats, body)


@router.post("/funnel-plot", response_class=Response, responses=FILE_RESPONSE)  # type: ignore[arg-type]
async def analysis_funnel_plot(
    body: publication_bias.FunnelIn,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
    stats: StatsClient = Depends(get_stats_client),
) -> Response:
    """Funnel plot (SVG, or PNG at 300 dpi)."""
    content, media, name = await publication_bias.funnel_plot(session, ctx, stats, body)
    disposition = f"attachment; filename=\"{name}\"; filename*=UTF-8''{quote(name)}"
    return Response(content=content, media_type=media, headers={"Content-Disposition": disposition})


# ---- History (saved analyses) and the reproducible R script ---------------------------


@router.post("", status_code=status.HTTP_201_CREATED)
async def save_analysis(
    body: history.SaveIn,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
    stats: StatsClient = Depends(get_stats_client),
) -> history.AnalysisOut:
    """Runs and saves the analysis with its data, parameters, result and versions."""
    return await history.save(session, ctx, stats, body)


@router.get("")
async def list_analyses(
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> list[history.AnalysisSummary]:
    """Saved analyses, newest first, each saying whether its data changed since."""
    return await history.history(session, ctx)


@router.get("/{analysis_id}")
async def get_analysis(
    analysis_id: uuid.UUID,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> history.AnalysisOut:
    return await history.detail(session, ctx, analysis_id)


@router.delete("/{analysis_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_analysis(
    analysis_id: uuid.UUID,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Removes it from the history (soft delete: nothing is erased)."""
    await history.delete(session, ctx, analysis_id)


@router.get("/{analysis_id}/r-script", response_class=Response, responses=FILE_RESPONSE)  # type: ignore[arg-type]
async def analysis_r_script(
    analysis_id: uuid.UUID,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
    stats: StatsClient = Depends(get_stats_client),
) -> Response:
    """A .R file that reproduces the saved analysis in a clean R session."""
    script, name = await history.r_script(session, ctx, stats, analysis_id)
    disposition = f"attachment; filename=\"{name}\"; filename*=UTF-8''{quote(name)}"
    return Response(
        content=script.encode("utf-8"),
        media_type="text/x-r; charset=utf-8",
        headers={"Content-Disposition": disposition},
    )
