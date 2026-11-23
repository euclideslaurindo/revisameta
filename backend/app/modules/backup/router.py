import uuid

from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.integrations.queue import JobQueue, get_job_queue
from app.integrations.storage import Storage, get_storage
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.backup import service
from app.modules.projects import retention
from app.modules.projects.access import ProjectContext, member_access

router = APIRouter(tags=["backup"])


@router.post("/projects/{project_id}/backups", status_code=status.HTTP_202_ACCEPTED)
async def start_backup(
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
    queue: JobQueue = Depends(get_job_queue),
) -> service.BackupStarted:
    """Starts a full backup (data + PDFs) as a ZIP in the background. Admin."""
    return await service.start_backup(session, ctx, queue)


@router.get("/projects/{project_id}/backups/{job_id}/download")
async def backup_download(
    job_id: uuid.UUID,
    ctx: ProjectContext = Depends(member_access),
    session: AsyncSession = Depends(get_session),
    storage: Storage = Depends(get_storage),
) -> service.DownloadOut:
    """Short-lived link to download a finished backup. Admin."""
    return await service.download(session, ctx, storage, job_id)


@router.post("/projects/import", status_code=status.HTTP_202_ACCEPTED)
async def import_project(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    storage: Storage = Depends(get_storage),
    queue: JobQueue = Depends(get_job_queue),
) -> service.ImportStarted:
    """Creates a new project from a backup ZIP; whoever imports becomes its admin."""
    return await service.start_import(session, user, storage, queue, file)


@router.post("/projects/{project_id}/unarchive", status_code=status.HTTP_204_NO_CONTENT)
async def unarchive_project(
    ctx: ProjectContext = Depends(member_access), session: AsyncSession = Depends(get_session)
) -> None:
    """Removes the 'archived' mark of an inactive project. Admin."""
    await retention.unarchive(session, ctx)
