import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.integrations.queue import JobQueue, get_job_queue
from app.integrations.storage import Storage, get_storage
from app.modules.jobs.schemas_out import job_out
from app.modules.projects.access import ProjectContext, member_access, project_access
from app.modules.projects.models import Role
from app.modules.uploads import service
from app.modules.uploads.schemas import (
    DownloadUrl,
    JobOut,
    PartUrl,
    PartUrlsIn,
    UploadCreate,
    UploadOut,
    UploadState,
)

router = APIRouter(prefix="/projects/{project_id}/uploads", tags=["uploads"])

uploader_access = project_access(Role.REVIEWER, Role.EXTRACTOR)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_upload(
    body: UploadCreate,
    ctx: ProjectContext = Depends(uploader_access),
    session: AsyncSession = Depends(get_session),
    storage: Storage = Depends(get_storage),
) -> UploadOut:
    """Start a PDF upload. The browser then sends each part straight to storage."""
    return UploadOut.model_validate(await service.create_upload(session, storage, ctx, body))


@router.get("/{upload_id}")
async def get_upload(
    upload_id: uuid.UUID,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
    storage: Storage = Depends(get_storage),
) -> UploadState:
    """Status plus the parts already stored: after a connection drop, send only the rest."""
    upload = await service.get_upload(session, ctx, upload_id)
    return await service.upload_state(storage, upload)


@router.post("/{upload_id}/parts")
async def part_urls(
    upload_id: uuid.UUID,
    body: PartUrlsIn,
    ctx: ProjectContext = Depends(uploader_access),
    session: AsyncSession = Depends(get_session),
    storage: Storage = Depends(get_storage),
) -> list[PartUrl]:
    upload = await service.get_upload(session, ctx, upload_id)
    return await service.part_urls(storage, upload, body.part_numbers)


@router.post("/{upload_id}/complete", status_code=status.HTTP_202_ACCEPTED)
async def complete_upload(
    upload_id: uuid.UUID,
    ctx: ProjectContext = Depends(uploader_access),
    session: AsyncSession = Depends(get_session),
    storage: Storage = Depends(get_storage),
    queue: JobQueue = Depends(get_job_queue),
) -> JobOut:
    upload = await service.get_upload(session, ctx, upload_id)
    return job_out(await service.complete_upload(session, storage, queue, upload))


@router.delete("/{upload_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_upload(
    upload_id: uuid.UUID,
    ctx: ProjectContext = Depends(uploader_access),
    session: AsyncSession = Depends(get_session),
    storage: Storage = Depends(get_storage),
) -> None:
    upload = await service.get_upload(session, ctx, upload_id)
    await service.cancel_upload(session, storage, upload)


@router.get("/{upload_id}/download-url")
async def download_url(
    upload_id: uuid.UUID,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
    storage: Storage = Depends(get_storage),
) -> DownloadUrl:
    """Short-lived signed URL; PDFs are never public (docs/riscos.md, 10.2)."""
    upload = await service.get_upload(session, ctx, upload_id)
    url = await service.download_url(session, storage, upload)
    return DownloadUrl(url=url, expires_in=service.DOWNLOAD_URL_TTL_SECONDS)
