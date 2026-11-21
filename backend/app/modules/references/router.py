import datetime as dt
import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.integrations.queue import JobQueue, get_job_queue
from app.integrations.storage import Storage, get_storage
from app.modules.projects.access import ProjectContext, member_access
from app.modules.references import dedup, service
from app.modules.references.dedup_rules import DedupSettings

router = APIRouter(prefix="/projects/{project_id}", tags=["references"])


@router.post("/searches", status_code=status.HTTP_201_CREATED)
async def import_search(
    file: UploadFile = File(...),
    database: str = Form(min_length=1, max_length=100),
    search_date: dt.date = Form(...),
    strategy: str | None = Form(default=None, max_length=20000),
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
    storage: Storage = Depends(get_storage),
    queue: JobQueue = Depends(get_job_queue),
) -> service.SearchOut:
    """Imports a search export (RIS, PubMed .nbib, BibTeX or CSV) in the background.

    Follow the progress with the returned job_id. Admin or reviewer.
    """
    return await service.create_search(
        session, ctx, storage, queue, file, database, search_date, strategy
    )


@router.get("/searches")
async def list_searches(
    ctx: ProjectContext = Depends(member_access), session: AsyncSession = Depends(get_session)
) -> list[service.SearchOut]:
    return await service.list_searches(session, ctx)


@router.get("/searches/{search_id}")
async def get_search(
    search_id: uuid.UUID,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> service.SearchDetail:
    """The search with the report of records that could not be read."""
    return await service.detail(session, ctx, search_id)


@router.delete("/searches/{search_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_search(
    search_id: uuid.UUID,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Removes the search and its references (soft delete)."""
    await service.delete_search(session, ctx, search_id)


@router.get("/references")
async def list_references(
    search_id: uuid.UUID | None = None,
    after: uuid.UUID | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> service.ReferencePage:
    """References imported from searches, in import order (cursor pagination)."""
    return await service.list_references(session, ctx, search_id, after, limit)


# ---- Deduplication -------------------------------------------------------------------


@router.get("/deduplication/settings")
async def get_dedup_settings(ctx: ProjectContext = Depends(member_access)) -> DedupSettings:
    return dedup.settings_of(ctx)


@router.put("/deduplication/settings")
async def put_dedup_settings(
    body: DedupSettings,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> DedupSettings:
    """Title similarity threshold (admin). Run the detection again afterwards."""
    return await dedup.update_settings(session, ctx, body)


@router.post("/deduplication/run")
async def run_deduplication(
    ctx: ProjectContext = Depends(member_access), session: AsyncSession = Depends(get_session)
) -> dedup.DedupRunOut:
    """Finds certain, probable and related pairs. Nothing is removed: a person decides."""
    return await dedup.run(session, ctx)


@router.get("/deduplication/pairs")
async def list_duplicate_pairs(
    kind: str | None = Query(default=None, pattern="^(certain|probable|related)$"),
    status: str | None = Query(default=None, pattern="^(pending|confirmed|rejected)$"),
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> list[dedup.DuplicatePairOut]:
    return await dedup.list_pairs(session, ctx, kind, status)


@router.post("/deduplication/pairs/{pair_id}")
async def decide_duplicate_pair(
    pair_id: uuid.UUID,
    body: dedup.DedupDecideIn,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
) -> dedup.DuplicatePairOut:
    """Confirm (saying which record stays), reject, or undo a decision."""
    return await dedup.decide(session, ctx, pair_id, body)


@router.post("/deduplication/confirm-certain")
async def confirm_certain_duplicates(
    ctx: ProjectContext = Depends(member_access), session: AsyncSession = Depends(get_session)
) -> dict[str, int]:
    """Confirms every pending pair with the same DOI or PMID (the first imported stays)."""
    return {"confirmed": await dedup.confirm_certain(session, ctx)}


@router.get("/deduplication/report")
async def deduplication_report(
    ctx: ProjectContext = Depends(member_access), session: AsyncSession = Depends(get_session)
) -> dedup.DedupReportOut:
    return await dedup.report(session, ctx)


@router.get(
    "/deduplication/report.csv",
    response_class=Response,
    responses={200: {"content": {"text/csv": {"schema": {"type": "string"}}}}},
)
async def deduplication_report_csv(
    ctx: ProjectContext = Depends(member_access), session: AsyncSession = Depends(get_session)
) -> Response:
    """Every pair with its criteria and decision, for the Methods section."""
    content = "﻿" + await dedup.report_csv(session, ctx)
    name = f"deduplicacao_{dt.date.today().isoformat()}.csv"
    return Response(
        content=content.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"},
    )
