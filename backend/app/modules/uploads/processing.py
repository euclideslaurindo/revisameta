"""Runs in the worker after an upload completes (docs/arquivos.md, 10.7).

1. Checks the real file type from the first bytes (not the extension).
2. Streams the object to compute SHA-256 without loading it in memory.
3. Deduplicates: the same content is stored once (`ref_count`).
4. Extracts the text of each page (pypdfium2), once per distinct file.
Progress is written to the job so the UI can follow it.
"""

import hashlib
import logging
import uuid

import magic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.integrations.storage import Storage
from app.modules.jobs.models import BackgroundJob, JobStatus
from app.modules.pdfs.text import extract_text
from app.modules.uploads.models import StoredFile, UploadSession, UploadStatus

logger = logging.getLogger(__name__)

HASH_CHUNK = 8 * 1024 * 1024
SNIFF_BYTES = 2048
PDF_MIME = "application/pdf"


def stored_key(sha256: str) -> str:
    return f"files/{sha256[:2]}/{sha256}.pdf"


async def _set_job(
    maker: async_sessionmaker[AsyncSession], job_id: uuid.UUID, **values: object
) -> None:
    async with maker() as session:
        job = await session.get(BackgroundJob, job_id)
        if job is not None:
            for key, value in values.items():
                setattr(job, key, value)
            await session.commit()


async def _fail(
    maker: async_sessionmaker[AsyncSession],
    storage: Storage,
    upload: UploadSession,
    job_id: uuid.UUID,
    code: str,
) -> None:
    await storage.delete(upload.storage_key)
    async with maker() as session:
        row = await session.get(UploadSession, upload.id)
        if row is not None:
            row.status = UploadStatus.FAILED
            row.error_code = code
            await session.commit()
    await _set_job(maker, job_id, status=JobStatus.FAILED, error_code=code)


async def process_upload(
    maker: async_sessionmaker[AsyncSession],
    storage: Storage,
    upload_id: uuid.UUID,
    job_id: uuid.UUID,
) -> None:
    async with maker() as session:
        upload = await session.get(UploadSession, upload_id)
    if upload is None:
        await _set_job(maker, job_id, status=JobStatus.FAILED, error_code="error.not_found")
        return
    await _set_job(maker, job_id, status=JobStatus.RUNNING, progress=1)

    head = await storage.read_range(upload.storage_key, 0, SNIFF_BYTES - 1)
    if magic.from_buffer(head, mime=True) != PDF_MIME:
        await _fail(maker, storage, upload, job_id, "upload.not_pdf")
        return

    digest = hashlib.sha256()
    read = 0
    last_reported = 0
    async for chunk in storage.iter_chunks(upload.storage_key, HASH_CHUNK):
        digest.update(chunk)
        read += len(chunk)
        progress = min(60, 1 + int(59 * read / max(upload.size_bytes, 1)))
        if progress - last_reported >= 5:
            last_reported = progress
            await _set_job(maker, job_id, progress=progress)
    sha256 = digest.hexdigest()

    async with maker() as session:
        existing = (
            await session.scalars(
                select(StoredFile).where(StoredFile.sha256 == sha256).with_for_update()
            )
        ).first()
        deduplicated = existing is not None
        if existing is not None:
            existing.ref_count += 1
            stored = existing
        else:
            key = stored_key(sha256)
            await storage.copy(upload.storage_key, key)
            stored = StoredFile(
                sha256=sha256, size_bytes=read, mime=PDF_MIME, storage_key=key, ref_count=1
            )
            session.add(stored)
            await session.flush()
        row = await session.get(UploadSession, upload.id)
        if row is None:  # pragma: no cover - the session row is never deleted
            raise RuntimeError(f"upload session {upload.id} disappeared")
        row.status = UploadStatus.DONE
        row.stored_file_id = stored.id
        await session.commit()
        stored_id = stored.id
        needs_text = stored.text_status in ("pending", "failed")

    await storage.delete(upload.storage_key)
    if needs_text:
        await _set_job(maker, job_id, progress=65)
        await extract_text(maker, storage, stored_id)
    async with maker() as session:
        final = await session.get(StoredFile, stored_id)
        page_count = final.page_count if final else None
        text_status = final.text_status if final else "failed"
    await _set_job(
        maker,
        job_id,
        status=JobStatus.SUCCEEDED,
        progress=100,
        result={
            "stored_file_id": str(stored_id),
            "sha256": sha256,
            "size_bytes": read,
            "deduplicated": deduplicated,
            "page_count": page_count,
            "text_status": text_status,
        },
    )
