import uuid
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.modules.exports import bibliography, extraction, risk_of_bias
from app.modules.projects.access import ProjectContext, member_access

router = APIRouter(prefix="/projects/{project_id}/exports", tags=["exports"])

FILE_RESPONSE = {
    200: {
        "description": "The exported file.",
        "content": {"application/octet-stream": {"schema": {"type": "string", "format": "binary"}}},
    }
}


@router.get("/extraction/status")
async def extraction_export_status(
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> extraction.ExportStatus:
    """Which studies have a submitted consensus and which would be left out."""
    return await extraction.export_status(session, ctx)


@router.get("/extraction", response_class=Response, responses=FILE_RESPONSE)  # type: ignore[arg-type]
async def export_extraction(
    file_format: Annotated[extraction.FileFormat, Query()] = extraction.FileFormat.XLSX,
    mode: Annotated[extraction.ExportMode, Query()] = extraction.ExportMode.CONSENSUS,
    csv_style: Annotated[extraction.CsvStyle, Query()] = extraction.CsvStyle.EXCEL,
    lang: Annotated[str | None, Query(max_length=8)] = None,
    acknowledge_missing: Annotated[bool, Query()] = False,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Extracted data as XLSX or CSV. Refuses to leave studies out silently."""
    content, name, media = await extraction.export_extraction(
        session,
        ctx,
        mode=mode,
        fmt=file_format,
        csv_style=csv_style,
        lang=lang,
        acknowledge_missing=acknowledge_missing,
    )
    disposition = f"attachment; filename=\"{name}\"; filename*=UTF-8''{quote(name)}"
    return Response(content=content, media_type=media, headers={"Content-Disposition": disposition})


@router.get("/bibliography/status")
async def bibliography_status(
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> bibliography.BibStatus:
    """How many records the bibliography has and which studies lack authors, year or
    journal."""
    return await bibliography.status(session, ctx)


@router.get("/bibliography", response_class=Response, responses=FILE_RESPONSE)  # type: ignore[arg-type]
async def export_bibliography(
    file_format: Annotated[bibliography.BibFormat, Query()] = bibliography.BibFormat.RIS,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Articles of the included studies as RIS, BibTeX or Vancouver text."""
    content, name, media = await bibliography.export(session, ctx, file_format)
    disposition = f"attachment; filename=\"{name}\"; filename*=UTF-8''{quote(name)}"
    return Response(content=content, media_type=media, headers={"Content-Disposition": disposition})


@router.get("/risk-of-bias", response_class=Response, responses=FILE_RESPONSE)  # type: ignore[arg-type]
async def export_risk_of_bias(
    tool_id: uuid.UUID,
    outcome_id: Annotated[uuid.UUID | None, Query()] = None,
    timepoint: Annotated[str | None, Query(max_length=60)] = None,
    file_format: Annotated[risk_of_bias.RobFormat, Query()] = risk_of_bias.RobFormat.XLSX,
    csv_style: Annotated[extraction.CsvStyle, Query()] = extraction.CsvStyle.EXCEL,
    lang: Annotated[str, Query(pattern="^(pt-BR|en)$")] = "pt-BR",
    acknowledge_missing: Annotated[bool, Query()] = False,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Consolidated risk of bias as robvis CSV, CSV, XLSX or DOCX. Never leaves studies out
    silently."""
    content, name, media = await risk_of_bias.export(
        session,
        ctx,
        tool_id=tool_id,
        outcome_id=outcome_id,
        timepoint=timepoint,
        fmt=file_format,
        csv_style=csv_style,
        lang=lang,
        acknowledge_missing=acknowledge_missing,
    )
    disposition = f"attachment; filename=\"{name}\"; filename*=UTF-8''{quote(name)}"
    return Response(content=content, media_type=media, headers={"Content-Disposition": disposition})
