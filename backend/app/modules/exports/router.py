from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.modules.exports import extraction
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
