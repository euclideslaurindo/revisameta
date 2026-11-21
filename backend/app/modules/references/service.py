"""Search import (docs/modulos.md 7.2; stage 5 step 1).

1. The request streams the file to storage and records the search (database, date,
   strategy); nothing is parsed in the request.
2. The worker reads the file line by line, writes references in batches of 500 and
   keeps a report of the records it could not read (first 200, with the reason),
   without stopping the import (docs/arquivos.md 10.7).

Imported references are written in bulk and audited once, through the search row
(who imported which file, how many records): a 20 thousand record search would
otherwise write 20 thousand audit snapshots.
"""

import codecs
import datetime as dt
import tempfile
import uuid
from collections.abc import Awaitable, Callable, Iterable, Iterator
from typing import Any

from fastapi import UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.errors import AppError, ForbiddenError, NotFoundError
from app.db.base import new_id
from app.integrations.queue import JobQueue
from app.integrations.storage import Storage
from app.modules.jobs.models import BackgroundJob, JobStatus
from app.modules.projects.access import ProjectContext
from app.modules.projects.models import Role
from app.modules.references.models import Search
from app.modules.references.parsers import READERS, Item, Record, detect_format
from app.modules.studies.models import Reference

MAX_SEARCH_BYTES = 100 * 1024 * 1024
BATCH = 500
MAX_ERRORS_KEPT = 200
CHUNK = 256 * 1024
IMPORTERS = {Role.ADMIN, Role.REVIEWER}


class SearchOut(BaseModel):
    id: uuid.UUID
    database: str
    search_date: dt.date
    strategy: str | None
    filename: str
    file_format: str
    status: str
    job_id: uuid.UUID | None
    record_count: int
    error_count: int  # records not imported
    warning_count: int  # records imported with a field left empty
    error_code: str | None
    created_at: dt.datetime
    created_by: uuid.UUID | None


class SearchDetail(SearchOut):
    errors: list[dict[str, Any]]  # {number, code, skipped}: first 200


class SearchReferenceOut(BaseModel):
    id: uuid.UUID
    search_id: uuid.UUID | None
    record_number: int | None
    title: str
    authors: str | None
    year: int | None
    doi: str | None
    pmid: str | None
    journal: str | None
    volume: str | None
    issue: str | None
    pages: str | None
    abstract: str | None
    keywords: str | None
    url: str | None


class ReferencePage(BaseModel):
    items: list[SearchReferenceOut]
    total: int
    next_cursor: uuid.UUID | None = Field(description="Pass as `after` for the next page")


def _out(s: Search, detail: bool = False) -> SearchOut:
    data = {k: getattr(s, k) for k in SearchOut.model_fields}
    if detail:
        return SearchDetail(**data, errors=s.errors or [])
    return SearchOut(**data)


def _can_import(ctx: ProjectContext) -> None:
    if not (IMPORTERS & ctx.roles):
        raise ForbiddenError()


async def create_search(
    session: AsyncSession,
    ctx: ProjectContext,
    storage: Storage,
    queue: JobQueue,
    file: UploadFile,
    database: str,
    search_date: dt.date,
    strategy: str | None,
) -> SearchOut:
    _can_import(ctx)
    size = file.size or 0
    if size > MAX_SEARCH_BYTES:
        raise AppError("import.too_large", status_code=413, limit=MAX_SEARCH_BYTES // 2**20)
    if size == 0:
        raise AppError("import.empty_file", status_code=422)
    head = (await file.read(4096)).decode("utf-8", errors="replace")
    await file.seek(0)
    file_format = detect_format(file.filename or "", head)
    if file_format is None:
        raise AppError("import.unknown_format", status_code=422)
    search_id = new_id()
    key = f"imports/{ctx.project.id}/{search_id}"
    await storage.put_fileobj(key, file.file, "text/plain")
    job = BackgroundJob(
        id=new_id(), project_id=ctx.project.id, kind="search_import", created_by=ctx.user.id
    )
    session.add(job)
    await session.flush()
    search = Search(
        id=search_id,
        project_id=ctx.project.id,
        database=database.strip(),
        search_date=search_date,
        strategy=(strategy or "").strip() or None,
        filename=(file.filename or "file")[:255],
        file_format=file_format,
        storage_key=key,
        job_id=job.id,
        created_by=ctx.user.id,
    )
    session.add(search)
    await session.commit()
    await queue.enqueue("import_search_task", search_id=str(search.id), job_id=str(job.id))
    await session.refresh(search)
    return _out(search)


async def _download(storage: Storage, key: str, target: Any) -> str:
    """Copies the file to a local temporary file in chunks and says its encoding:
    UTF-8 when all of it decodes as UTF-8, otherwise Windows-1252 (old exports)."""
    decoder: Any = codecs.getincrementaldecoder("utf-8")()
    utf8 = True
    async for chunk in storage.iter_chunks(key, CHUNK):
        target.write(chunk)
        if utf8:
            try:
                decoder.decode(chunk)
            except UnicodeDecodeError:
                utf8 = False
    target.flush()
    if utf8:
        try:
            decoder.decode(b"", final=True)
        except UnicodeDecodeError:
            utf8 = False
    return "utf-8-sig" if utf8 else "cp1252"


def _counting(lines: Iterator[str], seen: list[int]) -> Iterator[str]:
    for line in lines:
        seen[0] += len(line)
        yield line


async def _set(
    maker: async_sessionmaker[AsyncSession], model: Any, id_: uuid.UUID, **values: Any
) -> None:
    async with maker() as session:
        row = await session.get(model, id_)
        if row is not None:
            for key, value in values.items():
                setattr(row, key, value)
            await session.commit()


async def _read_items(
    items: Iterable[Item],
    rows: list[dict[str, Any]],
    errors: list[dict[str, Any]],
    flush: Callable[[], Awaitable[None]],
    base: dict[str, Any] | None = None,
) -> None:
    for item in items:
        if not isinstance(item, Record):
            errors.append({"number": item.number, "code": item.code, "skipped": True})
            continue
        for code in item.warnings:
            errors.append({"number": item.number, "code": code, "skipped": False})
        rows.append({**(base or {}), "id": new_id(), "record_number": item.number, **item.values})
        if len(rows) >= BATCH:
            await flush()


async def process_search(
    maker: async_sessionmaker[AsyncSession],
    storage: Storage,
    search_id: uuid.UUID,
    job_id: uuid.UUID,
) -> None:
    async with maker() as session:
        search = await session.get(Search, search_id)
    if search is None:
        await _set(
            maker, BackgroundJob, job_id, status=JobStatus.FAILED, error_code="error.not_found"
        )
        return
    await _set(maker, BackgroundJob, job_id, status=JobStatus.RUNNING, progress=1)
    await _set(maker, Search, search_id, status="running")
    total_bytes = max(await storage.size(search.storage_key), 1)
    read = [0]
    errors: list[dict[str, Any]] = []  # every error; only the first 200 are stored
    created = 0
    batch: list[dict[str, Any]] = []
    last_progress = 1

    async def flush() -> None:
        nonlocal created, last_progress
        if not batch:
            return
        async with maker() as session:
            await session.execute(insert(Reference), batch)
            await session.commit()
        created += len(batch)
        batch.clear()
        progress = min(99, 1 + int(98 * read[0] / total_bytes))
        if progress > last_progress:
            last_progress = progress
            await _set(maker, BackgroundJob, job_id, progress=progress)

    reader = READERS[search.file_format]
    try:
        with tempfile.NamedTemporaryFile(suffix=".import") as raw:
            encoding = await _download(storage, search.storage_key, raw)
            # Local temporary file in the worker: blocking reads are fine here.
            with open(raw.name, encoding=encoding, errors="replace", newline="") as text:  # noqa: ASYNC230
                base = {
                    "project_id": search.project_id,
                    "search_id": search.id,
                    "created_by": search.created_by,
                }
                await _read_items(reader(_counting(text, read)), batch, errors, flush, base)
        await flush()
    except Exception:
        async with maker() as session:
            await session.execute(
                update(Reference)
                .where(Reference.search_id == search.id)
                .values(deleted_at=func.now())
            )
            await session.commit()
        await _set(maker, Search, search_id, status="failed", error_code="import.read_failed")
        await _set(
            maker, BackgroundJob, job_id, status=JobStatus.FAILED, error_code="import.read_failed"
        )
        raise
    await _set(
        maker,
        Search,
        search_id,
        status="done",
        record_count=created,
        error_count=sum(1 for e in errors if e["skipped"]),
        warning_count=sum(1 for e in errors if not e["skipped"]),
        errors=errors[:MAX_ERRORS_KEPT],
    )
    await _set(
        maker,
        BackgroundJob,
        job_id,
        status=JobStatus.SUCCEEDED,
        progress=100,
        result={
            "search_id": str(search_id),
            "records": created,
            "errors": sum(1 for e in errors if e["skipped"]),
        },
    )


async def list_searches(session: AsyncSession, ctx: ProjectContext) -> list[SearchOut]:
    rows = await session.scalars(
        select(Search).where(Search.project_id == ctx.project.id).order_by(Search.created_at)
    )
    return [_out(s) for s in rows]


async def _get(session: AsyncSession, ctx: ProjectContext, search_id: uuid.UUID) -> Search:
    search = (
        await session.scalars(
            select(Search).where(Search.id == search_id, Search.project_id == ctx.project.id)
        )
    ).first()
    if search is None:
        raise NotFoundError()
    return search


async def detail(session: AsyncSession, ctx: ProjectContext, search_id: uuid.UUID) -> SearchDetail:
    out = _out(await _get(session, ctx, search_id), detail=True)
    assert isinstance(out, SearchDetail)  # noqa: S101 - detail=True builds it
    return out


async def delete_search(session: AsyncSession, ctx: ProjectContext, search_id: uuid.UUID) -> None:
    """Soft delete of the search and of its references (nothing is erased)."""
    _can_import(ctx)
    search = await _get(session, ctx, search_id)
    if search.status in ("queued", "running"):
        raise AppError("import.still_running", status_code=409)
    search.deleted_at = dt.datetime.now(dt.UTC)
    await session.execute(
        update(Reference)
        .where(Reference.search_id == search.id, Reference.deleted_at.is_(None))
        .values(deleted_at=func.now())
    )
    await session.commit()


async def list_references(
    session: AsyncSession,
    ctx: ProjectContext,
    search_id: uuid.UUID | None,
    after: uuid.UUID | None,
    limit: int,
) -> ReferencePage:
    """References imported from searches, in import order (cursor pagination)."""
    where = [Reference.project_id == ctx.project.id, Reference.search_id.is_not(None)]
    if search_id is not None:
        where.append(Reference.search_id == search_id)
    total = await session.scalar(select(func.count()).select_from(Reference).where(*where)) or 0
    query = select(Reference).where(*where)
    if after is not None:
        query = query.where(Reference.id > after)
    rows = list(await session.scalars(query.order_by(Reference.id).limit(limit + 1)))
    more = len(rows) > limit
    rows = rows[:limit]
    return ReferencePage(
        items=[SearchReferenceOut.model_validate(r, from_attributes=True) for r in rows],
        total=total,
        next_cursor=rows[-1].id if more and rows else None,
    )
