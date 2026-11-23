"""Project backup and re-import (docs/modulos.md 7.10; stage 6 step 6).

Backup: a ZIP made by the worker, never in the request's memory (10.7):
- manifest.json: format, version, database revision, date, counts per table;
- tables/<table>.jsonl: every row of every project table, soft-deleted rows and the
  audit log included, so nothing is lost;
- users.jsonl: id and name of the people who appear in the rows (never e-mails);
- stored_files.jsonl, pdf_page_texts.jsonl and files/<sha256>.pdf: the PDFs.
Left out on purpose: notifications, invitations (tokens) and background jobs, which
only make sense where they were created.

Re-import: creates a NEW project (the original may still exist in this system). Every
id gets a new value, also inside JSON columns (analysis plan, snapshots, mentions...),
by replacing the known ids in the row text. People who exist in this system keep their
records; people who do not are attributed to whoever imports, and the job result
lists their names. The backup must come from the same database revision.
"""

import datetime as dt
import io
import json
import re
import tempfile
import uuid
import zipfile
from collections.abc import Iterator
from decimal import Decimal
from enum import Enum
from typing import IO, Any

from fastapi import UploadFile
from pydantic import BaseModel
from sqlalchemy import Table, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.errors import AppError, ForbiddenError, NotFoundError
from app.db.base import Base, new_id
from app.integrations.queue import JobQueue
from app.integrations.storage import Storage
from app.modules.auth.models import User
from app.modules.jobs.models import BackgroundJob, JobStatus
from app.modules.projects.access import ProjectContext
from app.modules.projects.models import Project, ProjectMember, Role
from app.modules.uploads.models import PdfPageText, StoredFile
from app.modules.uploads.processing import stored_key

FORMAT = "revisameta-project-backup"
VERSION = 1
EXCLUDED = {"notifications", "invitations", "background_jobs"}
MAX_BACKUP_BYTES = 2 * 2**30
CHUNK = 8 * 2**20
STORED: Table = Base.metadata.tables["stored_files"]
PAGES: Table = Base.metadata.tables["pdf_page_texts"]
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
USER_TABLE = "users"


class BackupStarted(BaseModel):
    job_id: uuid.UUID


class ImportStarted(BaseModel):
    project_id: uuid.UUID
    job_id: uuid.UUID


class DownloadOut(BaseModel):
    url: str
    name: str
    size: int


def project_tables() -> list[Table]:
    """Project tables in foreign-key order (parents first)."""
    return [
        t for t in Base.metadata.sorted_tables if "project_id" in t.c and t.name not in EXCLUDED
    ]


def _plain(value: Any) -> Any:
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    if isinstance(value, (uuid.UUID, Decimal)):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    raise TypeError(type(value))


def _dump(row: dict[str, Any]) -> str:
    return json.dumps(row, default=_plain, ensure_ascii=False)


def _coerce(table: Table, row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, value in row.items():
        if name not in table.c:
            continue  # column that no longer exists (cannot happen with the same revision)
        if value is not None and isinstance(value, str):
            try:
                kind = table.c[name].type.python_type
            except NotImplementedError:
                kind = str
            if kind is dt.datetime:
                value = dt.datetime.fromisoformat(value)
            elif kind is dt.date:
                value = dt.date.fromisoformat(value)
            elif kind is Decimal:
                value = Decimal(value)
            elif kind is uuid.UUID:
                value = uuid.UUID(value)
        out[name] = value
    return out


async def _revision(session: AsyncSession) -> str:
    return str(await session.scalar(text("SELECT version_num FROM alembic_version")))


async def _set_job(
    maker: async_sessionmaker[AsyncSession], job_id: uuid.UUID, **values: Any
) -> None:
    async with maker() as session:
        job = await session.get(BackgroundJob, job_id)
        if job is not None:
            for key, value in values.items():
                setattr(job, key, value)
            await session.commit()


# ---- Backup ------------------------------------------------------------------------------


async def start_backup(
    session: AsyncSession, ctx: ProjectContext, queue: JobQueue
) -> BackupStarted:
    if not ctx.is_admin:
        raise ForbiddenError()
    job = BackgroundJob(
        id=new_id(), project_id=ctx.project.id, kind="project_backup", created_by=ctx.user.id
    )
    session.add(job)
    await session.commit()
    await queue.enqueue("project_backup_task", project_id=str(ctx.project.id), job_id=str(job.id))
    return BackupStarted(job_id=job.id)


def _slug(text_: str) -> str:
    from app.modules.exports.extraction import _slug as slug

    return slug(text_)


async def make_backup(
    maker: async_sessionmaker[AsyncSession],
    storage: Storage,
    project_id: uuid.UUID,
    job_id: uuid.UUID,
) -> None:
    await _set_job(maker, job_id, status=JobStatus.RUNNING, progress=1)
    try:
        await _make_backup(maker, storage, project_id, job_id)
    except Exception:
        await _set_job(maker, job_id, status=JobStatus.FAILED, error_code="backup.failed")
        raise


async def _make_backup(
    maker: async_sessionmaker[AsyncSession],
    storage: Storage,
    project_id: uuid.UUID,
    job_id: uuid.UUID,
) -> None:
    tables = [Base.metadata.tables["projects"], *project_tables()]
    user_columns = {
        (t.name, c.name)
        for t in tables
        for c in t.columns
        if any(fk.column.table.name == USER_TABLE for fk in c.foreign_keys)
    }
    counts: dict[str, int] = {}
    users: set[str] = set()
    stored_ids: set[uuid.UUID] = set()
    with tempfile.TemporaryFile() as tmp:
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            async with maker() as session:
                revision = await _revision(session)
                title = await session.scalar(select(Project.title).where(Project.id == project_id))
                for i, table in enumerate(tables):
                    key = table.c.id if table.name == "projects" else table.c.project_id
                    result = await session.stream(select(table).where(key == project_id))
                    n = 0
                    with zf.open(f"tables/{table.name}.jsonl", "w") as out:
                        async for row in result.mappings():
                            data = dict(row)
                            for t_name, c_name in user_columns:
                                if t_name == table.name and data.get(c_name):
                                    users.add(str(data[c_name]))
                            if table.name == "pdf_files" and data.get("stored_file_id"):
                                stored_ids.add(data["stored_file_id"])
                            out.write((_dump(data) + "\n").encode())
                            n += 1
                    counts[table.name] = n
                    await _set_job(maker, job_id, progress=1 + int(40 * (i + 1) / len(tables)))
                names = await session.execute(
                    select(User.id, User.name).where(User.id.in_([uuid.UUID(u) for u in users]))
                )
                with zf.open("users.jsonl", "w") as out:
                    for uid, name in names.all():
                        out.write((_dump({"id": uid, "name": name}) + "\n").encode())
                files = list(
                    await session.scalars(select(StoredFile).where(StoredFile.id.in_(stored_ids)))
                )
                texts = await session.stream(
                    select(PdfPageText.__table__).where(PdfPageText.stored_file_id.in_(stored_ids))
                )
                with zf.open("pdf_page_texts.jsonl", "w") as out:
                    async for row in texts.mappings():
                        out.write((_dump(dict(row)) + "\n").encode())
            with zf.open("stored_files.jsonl", "w") as out:
                for f in files:
                    meta = {c.name: getattr(f, c.name) for c in StoredFile.__table__.columns}
                    out.write((_dump(meta) + "\n").encode())
            for i, f in enumerate(files):
                with zf.open(f"files/{f.sha256}.pdf", "w") as out:
                    async for chunk in storage.iter_chunks(f.storage_key, CHUNK):
                        out.write(chunk)
                await _set_job(maker, job_id, progress=41 + int(50 * (i + 1) / max(len(files), 1)))
            manifest = {
                "format": FORMAT,
                "version": VERSION,
                "revision": revision,
                "exported_at": dt.datetime.now(dt.UTC).isoformat(),
                "project_id": str(project_id),
                "project_title": title,
                "counts": counts,
                "files": len(files),
            }
            zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        size = tmp.tell()
        tmp.seek(0)
        storage_key = f"backups/{project_id}/{job_id}.zip"
        await storage.put_fileobj(storage_key, tmp, "application/zip")
    day = dt.datetime.now(dt.UTC).strftime("%Y-%m-%d")
    name = f"{_slug(title or 'project')}_backup_{day}.zip"
    await _set_job(
        maker,
        job_id,
        status=JobStatus.SUCCEEDED,
        progress=100,
        result={
            "key": storage_key,
            "name": name,
            "size": size,
            "counts": counts,
            "files": len(files),
        },
    )


async def download(
    session: AsyncSession, ctx: ProjectContext, storage: Storage, job_id: uuid.UUID
) -> DownloadOut:
    if not ctx.is_admin:
        raise ForbiddenError()
    job = (
        await session.scalars(
            select(BackgroundJob).where(
                BackgroundJob.id == job_id,
                BackgroundJob.project_id == ctx.project.id,
                BackgroundJob.kind == "project_backup",
            )
        )
    ).first()
    if job is None or job.status != JobStatus.SUCCEEDED or not job.result:
        raise NotFoundError()
    r = job.result
    url = await storage.presign_get(
        r["key"], 600, r["name"], content_type="application/zip", disposition="attachment"
    )
    return DownloadOut(url=url, name=r["name"], size=r["size"])


# ---- Re-import ---------------------------------------------------------------------------


def _jsonl(zf: zipfile.ZipFile, name: str) -> Iterator[dict[str, Any]]:
    if name not in zf.namelist():
        return
    with zf.open(name) as f:
        for line in io.TextIOWrapper(f, encoding="utf-8"):
            if line.strip():
                yield json.loads(line)


def _manifest(zf: zipfile.ZipFile) -> dict[str, Any]:
    try:
        manifest: dict[str, Any] = json.loads(zf.read("manifest.json"))
    except (KeyError, ValueError) as error:
        raise AppError("backup.invalid", status_code=422) from error
    if manifest.get("format") != FORMAT or manifest.get("version") != VERSION:
        raise AppError("backup.invalid", status_code=422)
    return manifest


async def start_import(
    session: AsyncSession, user: User, storage: Storage, queue: JobQueue, file: UploadFile
) -> ImportStarted:
    size = file.size or 0
    if size > MAX_BACKUP_BYTES:
        raise AppError("import.too_large", status_code=413, limit=MAX_BACKUP_BYTES // 2**20)
    try:
        zf = zipfile.ZipFile(file.file)
    except zipfile.BadZipFile as error:
        raise AppError("backup.invalid", status_code=422) from error
    manifest = _manifest(zf)
    if manifest["revision"] != await _revision(session):
        raise AppError("backup.other_version", status_code=422)
    original = next(_jsonl(zf, "tables/projects.jsonl"), None)
    if original is None:
        raise AppError("backup.invalid", status_code=422)
    project = Project(
        title=str(original.get("title") or manifest.get("project_title") or "Projeto")[:300],
        owner_id=user.id,
        created_by=user.id,
    )
    session.add(project)
    await session.flush()
    session.add(
        ProjectMember(
            project_id=project.id, user_id=user.id, roles=[Role.ADMIN.value], created_by=user.id
        )
    )
    job = BackgroundJob(
        id=new_id(), project_id=project.id, kind="project_import", created_by=user.id
    )
    session.add(job)
    key = f"imports/backups/{job.id}.zip"
    await file.seek(0)
    await storage.put_fileobj(key, file.file, "application/zip")
    await session.commit()
    await queue.enqueue(
        "project_import_task",
        project_id=str(project.id),
        job_id=str(job.id),
        key=key,
        user_id=str(user.id),
    )
    return ImportStarted(project_id=project.id, job_id=job.id)


async def run_import(
    maker: async_sessionmaker[AsyncSession],
    storage: Storage,
    project_id: uuid.UUID,
    job_id: uuid.UUID,
    key: str,
    user_id: uuid.UUID,
) -> None:
    await _set_job(maker, job_id, status=JobStatus.RUNNING, progress=1)
    try:
        with tempfile.TemporaryFile() as tmp:
            async for chunk in storage.iter_chunks(key, CHUNK):
                tmp.write(chunk)
            tmp.seek(0)
            result = await _import(maker, storage, tmp, project_id, job_id, user_id)
    except AppError as error:
        await _set_job(maker, job_id, status=JobStatus.FAILED, error_code=error.code)
        return
    except Exception:
        await _set_job(maker, job_id, status=JobStatus.FAILED, error_code="backup.failed")
        raise
    finally:
        await storage.delete(key)
    await _set_job(maker, job_id, status=JobStatus.SUCCEEDED, progress=100, result=result)


def _remap(row: dict[str, Any], ids: dict[str, str]) -> dict[str, Any]:
    text_ = UUID_RE.sub(lambda m: ids.get(m.group(0), m.group(0)), _dump(row))
    loaded: dict[str, Any] = json.loads(text_)
    return loaded


async def _import(
    maker: async_sessionmaker[AsyncSession],
    storage: Storage,
    tmp: IO[bytes],
    project_id: uuid.UUID,
    job_id: uuid.UUID,
    user_id: uuid.UUID,
) -> dict[str, Any]:
    zf = zipfile.ZipFile(tmp)
    manifest = _manifest(zf)
    tables = project_tables()
    ids: dict[str, str] = {manifest["project_id"]: str(project_id)}
    for table in tables:
        for row in _jsonl(zf, f"tables/{table.name}.jsonl"):
            ids[row["id"]] = str(new_id())
    backup_users = {u["id"]: u["name"] for u in _jsonl(zf, "users.jsonl")}
    counts: dict[str, int] = {}
    async with maker() as session:
        existing = {
            str(u)
            for u in await session.scalars(
                select(User.id).where(User.id.in_([uuid.UUID(u) for u in backup_users]))
            )
        }
        absent = sorted(n for u, n in backup_users.items() if u not in existing)
        for u in backup_users:
            ids[u] = u if u in existing else str(user_id)

        # PDFs: reuse a file already stored here (same SHA-256), otherwise store it.
        for f in _jsonl(zf, "stored_files.jsonl"):
            found = (
                await session.scalars(
                    select(StoredFile).where(StoredFile.sha256 == f["sha256"]).with_for_update()
                )
            ).first()
            if found is not None:
                ids[f["id"]] = str(found.id)
                continue
            target = stored_key(f["sha256"])
            with zf.open(f"files/{f['sha256']}.pdf") as content:
                await storage.put_fileobj(target, content, "application/pdf")
            new = str(new_id())
            ids[f["id"]] = new
            row = _coerce(
                STORED,
                {**f, "id": new, "storage_key": target, "ref_count": 0},
            )
            await session.execute(STORED.insert().values(**row))
            pages = [
                _coerce(PAGES, {**_remap(p, ids), "id": str(new_id())})
                for p in _jsonl(zf, "pdf_page_texts.jsonl")
                if p["stored_file_id"] == f["id"]
            ]
            if pages:
                await session.execute(PAGES.insert(), pages)

        original = next(_jsonl(zf, "tables/projects.jsonl"))
        values = _coerce(Base.metadata.tables["projects"], _remap(original, ids))
        for keep in (
            "id",
            "owner_id",
            "created_by",
            "created_at",
            "version",
            "deleted_at",
            "archived_at",
        ):
            values.pop(keep, None)
        await session.execute(update(Project).where(Project.id == project_id).values(**values))

        for i, table in enumerate(tables):
            # Links to what a backup leaves out (jobs, upload sessions) are cleared.
            dangling = [
                c.name
                for c in table.columns
                if any(fk.column.table.name in EXCLUDED for fk in c.foreign_keys)
            ]
            batch: list[dict[str, Any]] = []
            n = 0
            seen_members: set[str] = {str(user_id)}
            for raw in _jsonl(zf, f"tables/{table.name}.jsonl"):
                row = _coerce(table, _remap(raw, ids))
                for name in dangling:
                    row[name] = None
                if table.name == "project_members":
                    member = str(row["user_id"])
                    if member in seen_members:
                        continue  # who imports is already admin of the new project
                    seen_members.add(member)
                batch.append(row)
                n += 1
                if len(batch) >= 500:
                    await session.execute(table.insert(), batch)
                    batch = []
            if batch:
                await session.execute(table.insert(), batch)
            counts[table.name] = n
            await _set_job(maker, job_id, progress=1 + int(95 * (i + 1) / len(tables)))

        # Each PDF file of the new project is one more reference to the stored file.
        refs = await session.execute(
            select(Base.metadata.tables["pdf_files"].c.stored_file_id, func.count())
            .where(Base.metadata.tables["pdf_files"].c.project_id == project_id)
            .group_by(Base.metadata.tables["pdf_files"].c.stored_file_id)
        )
        for stored_id, n in refs.all():
            await session.execute(
                update(StoredFile)
                .where(StoredFile.id == stored_id)
                .values(ref_count=StoredFile.ref_count + n)
            )
        await session.commit()
    return {"counts": counts, "absent_users": absent, "source_title": manifest.get("project_title")}
