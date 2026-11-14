import re
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ConflictError, ForbiddenError, NotFoundError
from app.integrations.storage import Storage
from app.modules.pdfs.models import PdfAnnotation, PdfFile
from app.modules.pdfs.schemas import (
    AnnotationIn,
    AnnotationUpdate,
    PdfOut,
    PdfViewOut,
    SearchHit,
)
from app.modules.pdfs.text import normalize_for_search
from app.modules.projects.access import ProjectContext
from app.modules.studies.models import Report
from app.modules.uploads.models import PdfPageText, StoredFile, UploadSession, UploadStatus

VIEW_URL_TTL_SECONDS = 600
SNIPPET_RADIUS = 80
MAX_HITS = 100


def _now() -> datetime:
    return datetime.now(UTC)


async def _report(session: AsyncSession, ctx: ProjectContext, report_id: uuid.UUID) -> Report:
    report = (
        await session.scalars(
            select(Report).where(Report.id == report_id, Report.project_id == ctx.project.id)
        )
    ).first()
    if report is None:
        raise NotFoundError()
    return report


async def _pdf(session: AsyncSession, ctx: ProjectContext, pdf_id: uuid.UUID) -> PdfFile:
    pdf = (
        await session.scalars(
            select(PdfFile).where(PdfFile.id == pdf_id, PdfFile.project_id == ctx.project.id)
        )
    ).first()
    if pdf is None:
        raise NotFoundError()
    return pdf


async def _out(session: AsyncSession, pdf: PdfFile) -> PdfOut:
    stored = await session.get(StoredFile, pdf.stored_file_id)
    assert stored is not None  # noqa: S101 - FK guarantees it
    return PdfOut(
        id=pdf.id,
        report_id=pdf.report_id,
        original_filename=pdf.original_filename,
        size_bytes=stored.size_bytes,
        page_count=stored.page_count,
        text_status=stored.text_status,
        created_at=pdf.created_at,
    )


async def attach(
    session: AsyncSession, ctx: ProjectContext, report_id: uuid.UUID, upload_id: uuid.UUID
) -> PdfOut:
    report = await _report(session, ctx, report_id)
    upload = (
        await session.scalars(
            select(UploadSession).where(
                UploadSession.id == upload_id, UploadSession.project_id == ctx.project.id
            )
        )
    ).first()
    if upload is None:
        raise NotFoundError()
    if upload.status != UploadStatus.DONE or upload.stored_file_id is None:
        raise AppError("pdf.upload_not_ready", status_code=409)
    pdf = PdfFile(
        project_id=ctx.project.id,
        created_by=ctx.user.id,
        report_id=report.id,
        stored_file_id=upload.stored_file_id,
        upload_session_id=upload.id,
        original_filename=upload.filename,
    )
    session.add(pdf)
    await session.commit()
    return await _out(session, pdf)


async def list_for_report(
    session: AsyncSession, ctx: ProjectContext, report_id: uuid.UUID
) -> list[PdfOut]:
    await _report(session, ctx, report_id)
    pdfs = await session.scalars(
        select(PdfFile).where(PdfFile.report_id == report_id).order_by(PdfFile.created_at)
    )
    return [await _out(session, p) for p in pdfs]


async def view(
    session: AsyncSession, storage: Storage, ctx: ProjectContext, pdf_id: uuid.UUID
) -> PdfViewOut:
    pdf = await _pdf(session, ctx, pdf_id)
    stored = await session.get(StoredFile, pdf.stored_file_id)
    assert stored is not None  # noqa: S101
    url = await storage.presign_get(stored.storage_key, VIEW_URL_TTL_SECONDS, pdf.original_filename)
    return PdfViewOut(
        **(await _out(session, pdf)).model_dump(), url=url, expires_in=VIEW_URL_TTL_SECONDS
    )


async def detach(session: AsyncSession, ctx: ProjectContext, pdf_id: uuid.UUID) -> None:
    pdf = await _pdf(session, ctx, pdf_id)
    pdf.deleted_at = _now()
    await session.commit()


def _snippet(content: str, start: int, end: int) -> str:
    left = max(0, start - SNIPPET_RADIUS)
    right = min(len(content), end + SNIPPET_RADIUS)
    text = " ".join(content[left:right].split())
    return ("…" if left > 0 else "") + text + ("…" if right < len(content) else "")


async def search(
    session: AsyncSession, ctx: ProjectContext, pdf_id: uuid.UUID, query: str
) -> list[SearchHit]:
    """Accent- and case-insensitive search that tolerates line breaks and hyphenation."""
    pdf = await _pdf(session, ctx, pdf_id)
    needle = normalize_for_search(query)
    if len(needle) < 2:
        raise AppError("error.validation", status_code=422)
    pattern = re.compile(re.escape(needle))
    pages = await session.scalars(
        select(PdfPageText)
        .where(PdfPageText.stored_file_id == pdf.stored_file_id)
        .order_by(PdfPageText.page)
    )
    hits: list[SearchHit] = []
    for page in pages:
        haystack = normalize_for_search(page.content)
        for match in pattern.finditer(haystack):
            hits.append(SearchHit(page=page.page, snippet=_snippet(haystack, *match.span())))
            if len(hits) >= MAX_HITS:
                return hits
    return hits


async def list_annotations(
    session: AsyncSession, ctx: ProjectContext, pdf_id: uuid.UUID
) -> list[PdfAnnotation]:
    await _pdf(session, ctx, pdf_id)
    rows = await session.scalars(
        select(PdfAnnotation)
        .where(PdfAnnotation.pdf_file_id == pdf_id)
        .order_by(PdfAnnotation.page, PdfAnnotation.created_at)
    )
    return list(rows)


async def create_annotation(
    session: AsyncSession, ctx: ProjectContext, pdf_id: uuid.UUID, data: AnnotationIn
) -> PdfAnnotation:
    pdf = await _pdf(session, ctx, pdf_id)
    stored = await session.get(StoredFile, pdf.stored_file_id)
    if stored is not None and stored.page_count and data.page > stored.page_count:
        raise AppError("error.validation", status_code=422)
    annotation = PdfAnnotation(
        project_id=ctx.project.id,
        created_by=ctx.user.id,
        pdf_file_id=pdf.id,
        user_id=ctx.user.id,
        page=data.page,
        quote=data.quote.strip(),
        rects=[r.model_dump() for r in data.rects],
        note=data.note,
        color=data.color,
    )
    session.add(annotation)
    await session.commit()
    return annotation


async def _own_annotation(
    session: AsyncSession, ctx: ProjectContext, annotation_id: uuid.UUID
) -> PdfAnnotation:
    annotation = (
        await session.scalars(
            select(PdfAnnotation).where(
                PdfAnnotation.id == annotation_id, PdfAnnotation.project_id == ctx.project.id
            )
        )
    ).first()
    if annotation is None:
        raise NotFoundError()
    if annotation.user_id != ctx.user.id and not ctx.is_admin:
        raise ForbiddenError()
    return annotation


async def update_annotation(
    session: AsyncSession, ctx: ProjectContext, annotation_id: uuid.UUID, data: AnnotationUpdate
) -> PdfAnnotation:
    annotation = await _own_annotation(session, ctx, annotation_id)
    if annotation.version != data.version:
        raise ConflictError()
    for key, value in data.model_dump(exclude_unset=True, exclude={"version"}).items():
        setattr(annotation, key, value)
    await session.commit()
    return annotation


async def delete_annotation(
    session: AsyncSession, ctx: ProjectContext, annotation_id: uuid.UUID
) -> None:
    annotation = await _own_annotation(session, ctx, annotation_id)
    annotation.deleted_at = _now()
    await session.commit()
