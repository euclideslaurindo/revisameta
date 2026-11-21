import datetime as dt
import uuid

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.integrations.queue import JobQueue, get_job_queue
from app.integrations.storage import Storage, get_storage
from app.modules.projects.access import ProjectContext, member_access
from app.modules.references import service

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
