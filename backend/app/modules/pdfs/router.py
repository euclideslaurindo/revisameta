"""PDFs of articles: members read; reviewers, extractors and admins attach and annotate."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.integrations.storage import Storage, get_storage
from app.modules.pdfs import service
from app.modules.pdfs.schemas import (
    AnnotationIn,
    AnnotationOut,
    AnnotationUpdate,
    AttachPdfIn,
    PdfOut,
    PdfViewOut,
    SearchHit,
)
from app.modules.projects.access import ProjectContext, member_access, project_access
from app.modules.projects.models import Role

router = APIRouter(prefix="/projects/{project_id}", tags=["pdfs"])

worker_access = project_access(Role.REVIEWER, Role.EXTRACTOR)


@router.post("/reports/{report_id}/pdfs", status_code=status.HTTP_201_CREATED)
async def attach_pdf(
    report_id: uuid.UUID,
    body: AttachPdfIn,
    ctx: ProjectContext = Depends(worker_access),
    session: AsyncSession = Depends(get_session),
) -> PdfOut:
    """Links a finished upload to an article."""
    return await service.attach(session, ctx, report_id, body.upload_id)


@router.get("/reports/{report_id}/pdfs")
async def list_pdfs(
    report_id: uuid.UUID,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> list[PdfOut]:
    return await service.list_for_report(session, ctx, report_id)


@router.get("/pdfs/{pdf_id}")
async def view_pdf(
    pdf_id: uuid.UUID,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
    storage: Storage = Depends(get_storage),
) -> PdfViewOut:
    """Metadata plus a short-lived signed URL; PDFs are never public."""
    return await service.view(session, storage, ctx, pdf_id)


@router.delete("/pdfs/{pdf_id}", status_code=status.HTTP_204_NO_CONTENT)
async def detach_pdf(
    pdf_id: uuid.UUID,
    ctx: ProjectContext = Depends(worker_access),
    session: AsyncSession = Depends(get_session),
) -> None:
    await service.detach(session, ctx, pdf_id)


@router.get("/pdfs/{pdf_id}/search")
async def search_pdf(
    pdf_id: uuid.UUID,
    q: str = Query(min_length=2, max_length=200),
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> list[SearchHit]:
    return await service.search(session, ctx, pdf_id, q)


@router.get("/pdfs/{pdf_id}/annotations")
async def list_annotations(
    pdf_id: uuid.UUID,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> list[AnnotationOut]:
    return [
        AnnotationOut.model_validate(a)
        for a in await service.list_annotations(session, ctx, pdf_id)
    ]


@router.post("/pdfs/{pdf_id}/annotations", status_code=status.HTTP_201_CREATED)
async def create_annotation(
    pdf_id: uuid.UUID,
    body: AnnotationIn,
    ctx: ProjectContext = Depends(worker_access),
    session: AsyncSession = Depends(get_session),
) -> AnnotationOut:
    return AnnotationOut.model_validate(await service.create_annotation(session, ctx, pdf_id, body))


@router.patch("/annotations/{annotation_id}")
async def update_annotation(
    annotation_id: uuid.UUID,
    body: AnnotationUpdate,
    ctx: ProjectContext = Depends(worker_access),
    session: AsyncSession = Depends(get_session),
) -> AnnotationOut:
    """Only the author (or a project admin) edits an annotation."""
    return AnnotationOut.model_validate(
        await service.update_annotation(session, ctx, annotation_id, body)
    )


@router.delete("/annotations/{annotation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_annotation(
    annotation_id: uuid.UUID,
    ctx: ProjectContext = Depends(worker_access),
    session: AsyncSession = Depends(get_session),
) -> None:
    await service.delete_annotation(session, ctx, annotation_id)
