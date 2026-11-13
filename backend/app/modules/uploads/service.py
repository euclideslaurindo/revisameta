"""Resumable multipart uploads straight to storage (ADR-004, docs/arquivos.md 10.7)."""

import math
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError, NotFoundError
from app.db.base import new_id
from app.integrations.queue import JobQueue
from app.integrations.storage import Storage
from app.modules.jobs.models import BackgroundJob
from app.modules.projects.access import ProjectContext
from app.modules.uploads.models import StoredFile, UploadSession, UploadStatus
from app.modules.uploads.schemas import PartUrl, UploadCreate, UploadState

PART_URL_TTL_SECONDS = 3600
DOWNLOAD_URL_TTL_SECONDS = 300
MB = 1024 * 1024
S3_MAX_PARTS = 10_000


def _now() -> datetime:
    return datetime.now(UTC)


async def storage_used_bytes(session: AsyncSession, user_id: uuid.UUID) -> int:
    """Finished files (each distinct file counted once) plus space reserved by open uploads."""
    finished = await session.scalar(
        select(func.coalesce(func.sum(StoredFile.size_bytes), 0)).where(
            StoredFile.id.in_(
                select(UploadSession.stored_file_id).where(
                    UploadSession.user_id == user_id,
                    UploadSession.status == UploadStatus.DONE,
                )
            )
        )
    )
    reserved = await session.scalar(
        select(func.coalesce(func.sum(UploadSession.size_bytes), 0)).where(
            UploadSession.user_id == user_id,
            UploadSession.status.in_([UploadStatus.UPLOADING, UploadStatus.PROCESSING]),
        )
    )
    return int(finished or 0) + int(reserved or 0)


def _validate(data: UploadCreate) -> None:
    max_bytes = get_settings().pdf_max_size_mb * MB
    if data.size_bytes > max_bytes:
        raise AppError("upload.too_large", status_code=413, limit=get_settings().pdf_max_size_mb)
    if not data.filename.lower().endswith(".pdf") or data.content_type != "application/pdf":
        raise AppError("upload.not_pdf", status_code=415)


async def create_upload(
    session: AsyncSession, storage: Storage, ctx: ProjectContext, data: UploadCreate
) -> UploadSession:
    from app.modules.quotas.service import ensure_storage_available

    _validate(data)
    await ensure_storage_available(session, ctx.user.id, data.size_bytes)

    part_size = get_settings().upload_part_size_mb * MB
    part_count = max(1, math.ceil(data.size_bytes / part_size))
    if part_count > S3_MAX_PARTS:  # pragma: no cover - impossible with sane limits
        raise AppError("upload.too_large", status_code=413, limit=get_settings().pdf_max_size_mb)

    upload_id = new_id()
    # System-generated key: the user's file name never reaches the storage path.
    key = f"incoming/{ctx.project.id}/{upload_id}"
    s3_upload_id = await storage.create_multipart(key, "application/pdf")
    upload = UploadSession(
        id=upload_id,
        project_id=ctx.project.id,
        user_id=ctx.user.id,
        created_by=ctx.user.id,
        filename=data.filename,
        size_bytes=data.size_bytes,
        part_size=part_size,
        part_count=part_count,
        storage_key=key,
        s3_upload_id=s3_upload_id,
        status=UploadStatus.UPLOADING,
        expires_at=_now() + timedelta(hours=get_settings().upload_session_ttl_hours),
    )
    session.add(upload)
    await session.commit()
    return upload


async def get_upload(
    session: AsyncSession, ctx: ProjectContext, upload_id: uuid.UUID
) -> UploadSession:
    upload = (
        await session.scalars(
            select(UploadSession).where(
                UploadSession.id == upload_id, UploadSession.project_id == ctx.project.id
            )
        )
    ).first()
    if upload is None:
        raise NotFoundError()
    return upload


def _ensure_open(upload: UploadSession) -> None:
    if upload.status != UploadStatus.UPLOADING:
        raise AppError("upload.expired", status_code=409)
    if upload.expires_at < _now():
        raise AppError("upload.expired", status_code=410)


async def upload_state(storage: Storage, upload: UploadSession) -> UploadState:
    state = UploadState.model_validate(upload)
    if upload.status == UploadStatus.UPLOADING:
        parts = await storage.list_parts(upload.storage_key, upload.s3_upload_id)
        state.uploaded_parts = sorted(p.number for p in parts)
    return state


async def part_urls(storage: Storage, upload: UploadSession, numbers: list[int]) -> list[PartUrl]:
    _ensure_open(upload)
    if any(n < 1 or n > upload.part_count for n in numbers):
        raise AppError("error.validation", status_code=422)
    return [
        PartUrl(
            part_number=n,
            url=await storage.presign_part(
                upload.storage_key, upload.s3_upload_id, n, PART_URL_TTL_SECONDS
            ),
        )
        for n in sorted(set(numbers))
    ]


def _expected_size(upload: UploadSession, number: int) -> int:
    if number < upload.part_count:
        return upload.part_size
    return upload.size_bytes - upload.part_size * (upload.part_count - 1)


async def complete_upload(
    session: AsyncSession, storage: Storage, queue: JobQueue, upload: UploadSession
) -> BackgroundJob:
    """Checks with the storage (not the browser) that every part arrived, then queues processing."""
    _ensure_open(upload)
    parts = {p.number: p for p in await storage.list_parts(upload.storage_key, upload.s3_upload_id)}
    complete = all(
        n in parts and parts[n].size == _expected_size(upload, n)
        for n in range(1, upload.part_count + 1)
    )
    if not complete:
        raise AppError("upload.incomplete", status_code=409)

    await storage.complete_multipart(
        upload.storage_key, upload.s3_upload_id, [parts[n] for n in sorted(parts)]
    )
    job = BackgroundJob(
        id=new_id(), project_id=upload.project_id, kind="process_upload", created_by=upload.user_id
    )
    session.add(job)
    upload.status = UploadStatus.PROCESSING
    upload.job_id = job.id
    await session.commit()
    await queue.enqueue("process_upload_task", upload_id=str(upload.id), job_id=str(job.id))
    return job


async def cancel_upload(session: AsyncSession, storage: Storage, upload: UploadSession) -> None:
    if upload.status == UploadStatus.UPLOADING:
        await storage.abort_multipart(upload.storage_key, upload.s3_upload_id)
        upload.status = UploadStatus.CANCELLED
        await session.commit()


async def download_url(session: AsyncSession, storage: Storage, upload: UploadSession) -> str:
    if upload.status != UploadStatus.DONE or upload.stored_file_id is None:
        raise NotFoundError()
    stored = await session.get(StoredFile, upload.stored_file_id)
    if stored is None:
        raise NotFoundError()
    return await storage.presign_get(stored.storage_key, DOWNLOAD_URL_TTL_SECONDS, upload.filename)


async def expire_stale_uploads(session: AsyncSession, storage: Storage) -> int:
    """Aborts uploads left unfinished past their expiry (frees storage and quota)."""
    stale = (
        await session.scalars(
            select(UploadSession).where(
                UploadSession.status == UploadStatus.UPLOADING, UploadSession.expires_at < _now()
            )
        )
    ).all()
    for upload in stale:
        await storage.abort_multipart(upload.storage_key, upload.s3_upload_id)
        upload.status = UploadStatus.EXPIRED
    await session.commit()
    return len(stale)
